from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='dead_stock_days',
            field=models.IntegerField(default=90, help_text='Mark as dead stock if no sale in this many days'),
        ),
    ]
