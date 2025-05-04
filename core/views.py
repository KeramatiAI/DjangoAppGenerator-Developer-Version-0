from django.shortcuts import render, redirect
from django.db import models, connection
from django.apps import apps
from django import forms
from django.urls import path, resolve, Resolver404
from django.core.exceptions import ValidationError
from django.db.models import Q
import os
import re
from .models import DynamicModel
import csv
from django.http import HttpResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


dynamic_urls = {}


class ModelGeneratorForm(forms.Form):
    model_name = forms.CharField(max_length=100, label="نام مدل")
    fields = forms.CharField(widget=forms.Textarea, label="فیلدها (مثال: name:CharField, price:IntegerField)")

    def clean_model_name(self):
        model_name = self.cleaned_data['model_name']
        if not re.match(r'^[a-zA-Z0-9_]+$', model_name):
            raise forms.ValidationError("نام مدل فقط می‌تواند شامل حروف، اعداد و زیرخط باشد.")
        return model_name

    def clean_fields(self):
        fields_input = self.cleaned_data['fields']
        allowed_field_types = [
            'CharField', 'IntegerField', 'FloatField', 'BooleanField',
            'DateField', 'DateTimeField', 'EmailField', 'TextField'
        ]
        field_pattern = re.compile(r'^[a-zA-Z0-9_]+:[a-zA-Z0-9_]+$')

        for line in fields_input.splitlines():
            if not field_pattern.match(line):
                raise forms.ValidationError("هر خط باید به صورت 'name:FieldType' باشد (مثل name:CharField).")
            name, field_type = line.split(':')
            if field_type not in allowed_field_types:
                raise forms.ValidationError(
                    f"نوع فیلد {field_type} مجاز نیست. فقط {', '.join(allowed_field_types)} مجازند.")
        return fields_input


def create_dynamic_model(model_name, fields_input):
    fields = {}
    for line in fields_input.splitlines():
        name, field_type = line.split(':')
        if field_type == 'CharField':
            fields[name] = models.CharField(max_length=255)
        elif field_type == 'IntegerField':
            fields[name] = models.IntegerField()
        elif field_type == 'FloatField':
            fields[name] = models.FloatField()
        elif field_type == 'BooleanField':
            fields[name] = models.BooleanField()
        elif field_type == 'DateField':
            fields[name] = models.DateField()
        elif field_type == 'DateTimeField':
            fields[name] = models.DateTimeField()
        elif field_type == 'EmailField':
            fields[name] = models.EmailField()
        elif field_type == 'TextField':
            fields[name] = models.TextField()

    attrs = {'__module__': 'core.models'}
    attrs.update(fields)
    dynamic_model = type(model_name, (models.Model,), attrs)

    app_config = apps.get_app_config('core')
    app_config.models[model_name.lower()] = dynamic_model

    create_table_manually(model_name, fields)

    return dynamic_model


def create_table_manually(model_name, fields):
    table_name = f'core_{model_name.lower()}'
    sql_fields = []
    for name, field in fields.items():
        if isinstance(field, models.CharField):
            sql_fields.append(f"{name} VARCHAR(255)")
        elif isinstance(field, models.IntegerField):
            sql_fields.append(f"{name} INTEGER")
        elif isinstance(field, models.FloatField):
            sql_fields.append(f"{name} REAL")
        elif isinstance(field, models.BooleanField):
            sql_fields.append(f"{name} INTEGER")  # SQLite بولین رو به‌صورت 0/1 ذخیره می‌کنه
        elif isinstance(field, models.DateField):
            sql_fields.append(f"{name} DATE")
        elif isinstance(field, models.DateTimeField):
            sql_fields.append(f"{name} DATETIME")
        elif isinstance(field, models.EmailField):
            sql_fields.append(f"{name} VARCHAR(255)")
        elif isinstance(field, models.TextField):
            sql_fields.append(f"{name} TEXT")

    sql_fields_str = ', '.join(sql_fields)
    sql = f"CREATE TABLE IF NOT EXISTS {table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT, {sql_fields_str})"

    with connection.cursor() as cursor:
        cursor.execute(sql)
    print(f"Table {table_name} created manually.")


def create_dynamic_form(dynamic_model):
    class DynamicForm(forms.ModelForm):
        class Meta:
            model = dynamic_model
            fields = '__all__'

    return DynamicForm


def dynamic_form_view(request, model_name):
    try:
        dynamic_model = apps.get_model('core', model_name)
        DynamicForm = create_dynamic_form(dynamic_model)

        if request.method == "POST":
            form = DynamicForm(request.POST)
            if form.is_valid():
                form.save()
                return render(request, 'core/dynamic_form.html', {
                    'form': DynamicForm(),
                    'model_name': model_name,
                    'message': f'داده برای {model_name} با موفقیت ذخیره شد!',
                    'list_url': f'/{model_name.lower()}/list/'
                })
        else:
            form = DynamicForm()
        return render(request, 'core/dynamic_form.html', {
            'form': form,
            'model_name': model_name,
            'list_url': f'/{model_name.lower()}/list/'
        })
    except LookupError:
        return render(request, 'core/error.html', {'message': f'مدل {model_name} پیدا نشد.'})


def generator_view(request):
    if request.method == "POST":
        form = ModelGeneratorForm(request.POST)
        if form.is_valid():
            model_name = form.cleaned_data['model_name']
            fields_input = form.cleaned_data['fields']
            try:
                if DynamicModel.objects.filter(name=model_name).exists():
                    raise ValidationError(f"مدل {model_name} قبلاً وجود دارد.")

                dynamic_model = create_dynamic_model(model_name, fields_input)

                DynamicModel.objects.create(name=model_name, fields=fields_input)

                url_path = f'{model_name.lower()}/form'
                dynamic_urls[url_path] = (dynamic_form_view, {'model_name': model_name})
                print(f"Registered dynamic URL: {url_path}")

                list_url_path = f'{model_name.lower()}/list'
                dynamic_urls[list_url_path] = (list_data_view, {'model_name': model_name})
                print(f"Registered dynamic URL: {list_url_path}")

                return redirect(f'/{url_path}/')
            except Exception as e:
                return render(request, 'core/generator.html', {
                    'form': form,
                    'message': f'خطا: {str(e)}',
                    'existing_models': DynamicModel.objects.all()
                })
    else:
        form = ModelGeneratorForm()
    return render(request, 'core/generator.html', {
        'form': form,
        'existing_models': DynamicModel.objects.all()
    })


def dynamic_url_resolver(request, path):
    print(f"Checking path: {path}")
    print(f"Current dynamic_urls: {dynamic_urls}")

    clean_path = path.rstrip('/')
    if clean_path in dynamic_urls:
        view_func, kwargs = dynamic_urls[clean_path]
        return view_func(request, **kwargs)

    # پشتیبانی از URL‌های صادرات CSV
    export_csv_pattern = re.compile(r'^([a-zA-Z0-9_]+)/export_csv$')
    match = export_csv_pattern.match(clean_path)
    if match:
        model_name = match.group(1)
        return export_csv_view(request, model_name)

    try:
        resolve(f'/{path}')
    except Resolver404:
        return render(request, 'core/error.html', {'message': f'مسیر {path} پیدا نشد.'})


def list_data_view(request, model_name):
    try:
        dynamic_model = apps.get_model('core', model_name)
        fields = [f.name for f in dynamic_model._meta.fields if f.name != 'id']
        field_types = {f.name: f.__class__.__module__ + '.' + f.__class__.__name__ for f in dynamic_model._meta.fields
                       if f.name != 'id'}

        search_query = request.GET.get('search', '')
        sort_field = request.GET.get('sort', '')
        sort_order = request.GET.get('order', 'asc')
        filters = {key: value for key, value in request.GET.items() if key.startswith('filter_') and value}

        data = dynamic_model.objects.all()

        # اعمال جستجو
        if search_query:
            query = Q()
            for field in fields:
                if isinstance(dynamic_model._meta.get_field(field),
                              (models.CharField, models.TextField, models.EmailField)):
                    query |= Q(**{f"{field}__icontains": search_query})
            data = data.filter(query)

        # اعمال فیلترها
        for filter_key, filter_value in filters.items():
            field_name = filter_key.replace('filter_', '')
            if field_name in fields:
                field_type = dynamic_model._meta.get_field(field_name)
                try:
                    if isinstance(field_type, models.BooleanField):
                        if filter_value.lower() in ('true', '1', 'on'):
                            data = data.filter(**{field_name: True})
                        elif filter_value.lower() in ('false', '0', 'off'):
                            data = data.filter(**{field_name: False})
                    elif isinstance(field_type, (models.IntegerField, models.FloatField)):
                        if '-' in filter_value:  # رنج (مثل 100-500)
                            min_val, max_val = map(float, filter_value.split('-'))
                            data = data.filter(**{f"{field_name}__gte": min_val, f"{field_name}__lte": max_val})
                        else:
                            data = data.filter(**{field_name: float(filter_value)})
                    elif isinstance(field_type, (models.DateField, models.DateTimeField)):
                        data = data.filter(**{f"{field_name}__exact": filter_value})
                    elif isinstance(field_type, (models.CharField, models.TextField, models.EmailField)):
                        data = data.filter(**{f"{field_name}__icontains": filter_value})
                except ValueError:
                    pass  # نادیده گرفتن مقادیر نامعتبر

        # اعمال مرتب‌سازی
        if sort_field in fields:
            order_prefix = '' if sort_order == 'asc' else '-'
            data = data.order_by(f"{order_prefix}{sort_field}")

        # صفحه‌بندی
        paginator = Paginator(data, 10)  # 10 داده در هر صفحه
        page = request.GET.get('page')
        try:
            paginated_data = paginator.page(page)
        except PageNotAnInteger:
            paginated_data = paginator.page(1)
        except EmptyPage:
            paginated_data = paginator.page(paginator.num_pages)

        formatted_data = [[getattr(item, field) for field in fields] for item in paginated_data]

        return render(request, 'core/list_data.html', {
            'model_name': model_name,
            'fields': fields,
            'field_types': field_types,
            'data': formatted_data,
            'search_query': search_query,
            'sort_field': sort_field,
            'sort_order': sort_order,
            'filters': filters,
            'paginated_data': paginated_data,  # برای ناوبری صفحه‌بندی
        })
    except LookupError:
        return render(request, 'core/error.html', {'message': f'مدل {model_name} پیدا نشد.'})


def export_csv_view(request, model_name):
    try:
        dynamic_model = apps.get_model('core', model_name)
        fields = [f.name for f in dynamic_model._meta.fields if f.name != 'id']
        data = dynamic_model.objects.all()

        # ایجاد پاسخ HTTP با نوع محتوا CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{model_name}_data.csv"'

        # نوشتن داده‌ها به CSV
        writer = csv.writer(response)
        writer.writerow(fields)  # نوشتن سرستون‌ها
        for item in data:
            writer.writerow([getattr(item, field) for field in fields])

        return response
    except LookupError:
        return render(request, 'core/error.html', {'message': f'مدل {model_name} پیدا نشد.'})

def edit_model_view(request, model_name):
    try:
        dynamic_model = DynamicModel.objects.get(name=model_name)
        if request.method == "POST":
            form = ModelGeneratorForm(request.POST)
            if form.is_valid():
                table_name = f'core_{model_name.lower()}'
                with connection.cursor() as cursor:
                    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")

                dynamic_model.fields = form.cleaned_data['fields']
                dynamic_model.save()

                create_dynamic_model(model_name, form.cleaned_data['fields'])

                return redirect('/')
        else:
            form = ModelGeneratorForm(initial={
                'model_name': model_name,
                'fields': dynamic_model.fields
            })
        return render(request, 'core/edit_model.html', {'form': form, 'model_name': model_name})
    except DynamicModel.DoesNotExist:
        return render(request, 'core/error.html', {'message': f'مدل {model_name} پیدا نشد.'})


def delete_model_view(request, model_name):
    try:
        dynamic_model = DynamicModel.objects.get(name=model_name)
        if request.method == "POST":
            table_name = f'core_{model_name.lower()}'
            with connection.cursor() as cursor:
                cursor.execute(f"DROP TABLE IF EXISTS {table_name}")

            dynamic_urls.pop(f'{model_name.lower()}/form', None)
            dynamic_urls.pop(f'{model_name.lower()}/list', None)

            dynamic_model.delete()
            return redirect('/')
        return render(request, 'core/delete_model.html', {'model_name': model_name})
    except DynamicModel.DoesNotExist:
        return render(request, 'core/error.html', {'message': f'مدل {model_name} پیدا نشد.'})


def edit_data_view(request, model_name, data_id):
    try:
        dynamic_model = apps.get_model('core', model_name)
        instance = dynamic_model.objects.get(id=data_id)
        DynamicForm = create_dynamic_form(dynamic_model)

        if request.method == "POST":
            form = DynamicForm(request.POST, instance=instance)
            if form.is_valid():
                form.save()
                return redirect(f'/{model_name.lower()}/list/')
        else:
            form = DynamicForm(instance=instance)
        return render(request, 'core/edit_data.html', {
            'form': form,
            'model_name': model_name,
            'data_id': data_id
        })
    except (LookupError, dynamic_model.DoesNotExist):
        return render(request, 'core/error.html', {'message': f'داده یا مدل {model_name} پیدا نشد.'})


def delete_data_view(request, model_name, data_id):
    try:
        dynamic_model = apps.get_model('core', model_name)
        instance = dynamic_model.objects.get(id=data_id)
        if request.method == "POST":
            instance.delete()
            return redirect(f'/{model_name.lower()}/list/')
        return render(request, 'core/delete_data.html', {
            'model_name': model_name,
            'data_id': data_id
        })
    except (LookupError, dynamic_model.DoesNotExist):
        return render(request, 'core/error.html', {'message': f'داده یا مدل {model_name} پیدا نشد.'})