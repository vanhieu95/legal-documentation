# Session management operations

The application stores authenticated sessions in Django's database session table. Application
requests enforce the 30-minute inactivity and eight-hour absolute limits before protected view code
runs.

Run Django's `clearsessions` command at least daily from the deployment scheduler to delete expired
database rows:

```bash
.venv/bin/python manage.py clearsessions --settings=config.settings.production
```

The operation is safe to retry. Monitor scheduler failures and database table growth. This cleanup
removes already-expired rows; it does not replace request-time expiry enforcement.
