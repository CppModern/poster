# Generated by Django 4.1.5 on 2023-01-06 20:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="myuser",
            name="special",
            field=models.BooleanField(default=False),
        ),
    ]
