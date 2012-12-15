
from simplejson.decoder import JSONDecodeError

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.template import RequestContext
from django.utils import simplejson

from tastypie.authorization import Authorization
from tastypie.resources import ModelResource
from tastypie import fields, http
from tastypie.exceptions import NotFound, BadRequest, InvalidFilterError, HydrationError, InvalidSortError, ImmediateHttpResponse, HttpResponse
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned, ValidationError
from tastypie.utils.mime import build_content_type


class GenericResource(ModelResource):
    def deserialize_post_data(self, request):
        '''
        Useful for get deserialized data
        '''
        return self.deserialize(request,
                                request.raw_post_data,
                                format=request.META.get('CONTENT_TYPE', 'application/json'))

    def determine_format(self, request):
        """
        Necessary to avoid the format=json attribute in the urli
        """
        return 'application/json'

    def wrap_form(self, form_class, method="POST"):
        """
        Creates a view for a given form class, which calls to is_valid()
        and save() when needed. You can get the form args reimplementing
        static_get_form_kwargs(request, data, *args, **kwargs) in your
        form.
        """
        @csrf_exempt
        def wrapper(request, *args, **kwargs):

            try:
                desired_format = self.determine_format(request)
                if method == "POST":
                    data = self.deserialize(request, request.raw_post_data,
                        desired_format)
                elif method == "GET":
                    data = request.GET
                response_data = {}
                if hasattr(form_class, "static_get_form_kwargs"):
                    kwargs = form_class.static_get_form_kwargs(request, data, 
                        *args, **kwargs)
                    form = form_class(**kwargs)
                else:
                    form = form_class(data=data)

                if not form.is_valid():
                    context = RequestContext(request, {})
                    context['form'] = form
                    errors = dict([(k, form.error_class.as_text(v)) for k, v in form.errors.items()])
                    response_data['errors'] = errors

                    serialized = self.serialize(request, response_data, desired_format)
                    return http.HttpBadRequest(serialized,
                        content_type=build_content_type(desired_format))

                else:
                    if hasattr(form, "save"):
                        form.save()

                return self.create_response(request, response_data)
            except JSONDecodeError, e:
                data = dict(errors=e.message)
                serialized = self.serialize(request, data, desired_format)
                return http.HttpBadRequest(serialized,
                        content_type=build_content_type(desired_format))
            except (BadRequest, fields.ApiFieldError), e:
                data = dict(errors=e.args[0])
                serialized = self.serialize(request, data, desired_format)
                return http.HttpBadRequest(serialized,
                        content_type=build_content_type(desired_format))
            except ValidationError, e:
                data = dict(errors=', '.join(e.messages))
                serialized = self.serialize(request, data, desired_format)
                return http.HttpBadRequest(serialized,
                        content_type=build_content_type(desired_format))
            except Exception, e:
                if hasattr(e, 'response'):
                    return e.response

                # A real, non-expected exception.
                # Handle the case where the full traceback is more helpful
                # than the serialized error.
                if settings.DEBUG and getattr(settings, 'TASTYPIE_FULL_DEBUG', False):
                    raise

                # Re-raise the error to get a proper traceback when the error
                # happend during a test case
                if request.META.get('SERVER_NAME') == 'testserver':
                    raise

                # Rather than re-raising, we're going to things similar to
                # what Django does. The difference is returning a serialized
                # error message.
                return self._handle_500(request, e)

        return wrapper

    def get_custom_list(self, request, list_url, queryset, kwargs):
        '''
        Generic function to list some object actions
        '''
        self.list_url = list_url
        self.queryset = queryset

        # Call to this generic internal tastypie function that does all the
        # heavy duty work
        out = self.get_list(request, **kwargs)
        delattr(self, 'list_url')
        delattr(self, 'queryset')

        return out

    def get_object_list(self, request):
        '''
        Called by get_list, see get_custom_list
        '''
        if not hasattr(self, 'queryset'):
            return self.Meta.queryset
        else:
            return self.queryset

    def get_resource_list_uri(self):
        '''
        Generates the URI for the resource list
        '''
        if hasattr(self, 'list_url'):
            return self.list_url
        else:
            return super(GenericResource, self).get_resource_list_uri()


class GenericMeta:
    list_allowed_methods = ['get', 'post']
    detail_allowed_methods = ['get', 'post', 'put', 'delete']
    # TODO When we have the first version of the API we could
    # work in the Authorization
    # authorization = DjangoAuthorization()
    authorization = Authorization()
    #authentication = SessionAuthentication()
    always_return_data = True
    include_resource_uri = False
