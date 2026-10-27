from django.db import migrations


def backfill_customer_branches(apps, schema_editor):
    Customer = apps.get_model('customers', 'Customer')
    Bill = apps.get_model('billing', 'Bill')

    for c in Customer.objects.filter(branch__isnull=True):
        # Find the latest bill associated with this customer
        bill = Bill.objects.filter(customer=c, branch__isnull=False).order_by('-id').first()
        if not bill and c.name:
            bill = Bill.objects.filter(customer_name=c.name, company=c.company, branch__isnull=False).order_by('-id').first()
        if bill and bill.branch:
            c.branch = bill.branch
            c.save(update_fields=['branch'])


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0003_customer_branch'),
        ('billing', '0002_bill_salesperson'),
    ]

    operations = [
        migrations.RunPython(backfill_customer_branches, migrations.RunPython.noop),
    ]
