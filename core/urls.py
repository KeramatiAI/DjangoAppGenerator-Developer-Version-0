from django.urls import path, re_path
from .views import generator_view, dynamic_url_resolver, edit_model_view, delete_model_view, edit_data_view, delete_data_view

urlpatterns = [
    path('', generator_view, name='generator'),
    path('<str:model_name>/edit/', edit_model_view, name='edit_model'),
    path('<str:model_name>/delete/', delete_model_view, name='delete_model'),
    path('<str:model_name>/data/<int:data_id>/edit/', edit_data_view, name='edit_data'),
    path('<str:model_name>/data/<int:data_id>/delete/', delete_data_view, name='delete_data'),
    re_path(r'^(?P<path>.+)/$', dynamic_url_resolver),
]