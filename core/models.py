from django.db import models

class DynamicModel(models.Model):
    name = models.CharField(max_length=100, unique=True)
    fields = models.TextField()  # ذخیره فیلدها به‌صورت رشته (مثل "name:CharField,price:IntegerField")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name