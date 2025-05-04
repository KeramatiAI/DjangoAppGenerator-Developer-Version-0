from django.apps import AppConfig
from django.db import DatabaseError, connection

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from .models import DynamicModel
        from .views import create_dynamic_model, dynamic_form_view, list_data_view
        from .views import dynamic_urls

        # مطمئن می‌شیم که دیتابیس آماده‌ست
        try:
            with connection.cursor():
                pass  # فقط چک می‌کنیم که اتصال برقراره
            for dynamic_model in DynamicModel.objects.all():
                model_name = dynamic_model.name
                fields_input = dynamic_model.fields

                # بازسازی مدل
                create_dynamic_model(model_name, fields_input)

                # ثبت URL‌ها
                url_path = f'{model_name.lower()}/form'
                dynamic_urls[url_path] = (dynamic_form_view, {'model_name': model_name})
                print(f"Re-registered dynamic URL: {url_path}")

                list_url_path = f'{model_name.lower()}/list'
                dynamic_urls[list_url_path] = (list_data_view, {'model_name': model_name})
                print(f"Re-registered dynamic URL: {list_url_path}")
        except (DatabaseError, Exception) as e:
            print(f"Error loading dynamic models: {e}")