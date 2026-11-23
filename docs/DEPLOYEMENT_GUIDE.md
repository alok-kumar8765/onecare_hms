# OneCare HMS — Live Server Deployment Guide

## 1. Prepare Environment Variables
Set these environment variables on your production server (via systemd `EnvironmentFile`, Docker env, or server environment):

```bash
export DJANGO_SETTINGS_MODULE=config.settings.prod
export SECRET_KEY="replace-with-a-long-random-production-secret-key"
export LICENSE_PUBLIC_KEY="replace-with-your-production-license-public-key"
export ALLOWED_HOSTS="hms.yourdomain.com,[www.yourdomain.com](https://www.yourdomain.com)"
export CSRF_TRUSTED_ORIGINS="[https://hms.yourdomain.com](https://hms.yourdomain.com),[https://www.yourdomain.com](https://www.yourdomain.com)"
export SECURE_SSL_REDIRECT="True"

# Database credentials (used when uncommenting PostgreSQL or MySQL in prod.py)
export DB_NAME="onecare_hms"
export DB_USER="onecare_user"
export DB_PASSWORD="strong-db-password"
export DB_HOST="127.0.0.1"
export DB_PORT="5432"
export DB_SSLMODE="prefer"

```
---

## 2. Enable PostgreSQL or MySQL in backend/config/settings/prod.py
Open backend/config/settings/prod.py, comment out the SQLite DATABASES block, and uncomment either the PostgreSQL block or the MySQL block:

- PostgreSQL (recommended for multi-branch concurrency & select_for_update()):
Install psycopg[binary] or psycopg2-binary in your server virtual environment, create the database and user, and uncomment the PostgreSQL DATABASES dictionary.

- MySQL / MariaDB:
Install mysqlclient or PyMySQL, create the database with utf8mb4, and uncomment the MySQL DATABASES dictionary.

---

## 3. Run Migrations, Static Collection & System Check
From backend/ inside your activated server virtual environment:

```bash
python manage.py makemigrations --settings=config.settings.prod
python manage.py migrate --settings=config.settings.prod
python manage.py collectstatic --noinput --settings=config.settings.prod
python manage.py check --deploy --settings=config.settings.prod
```

Create your initial platform SUPER_ADMIN user:

```bash
python manage.py createsuperuser --settings=config.settings.prod
```

---

## 4. Run with Gunicorn & Nginx (Reverse Proxy + TLS)
Start Gunicorn bound to a local socket or port (for example, 127.0.0.1:8001):

```bash
gunicorn config.wsgi:application \
  --bind 127.0.0.1:8001 \
  --workers 3 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -

```

Configure Nginx to terminate TLS/HTTPS, forward X-Forwarded-Proto $scheme, and serve staticfiles/ and media/:

```Nginx
server {
    listen 80;
    server_name hms.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name hms.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/[hms.yourdomain.com/fullchain.pem](https://hms.yourdomain.com/fullchain.pem);
    ssl_certificate_key /etc/letsencrypt/live/[hms.yourdomain.com/privkey.pem](https://hms.yourdomain.com/privkey.pem);

    client_max_body_size 15M;

    location /static/ {
        alias /opt/onecare-hms/backend/staticfiles/;
    }

    location /media/ {
        alias /opt/onecare-hms/backend/media/;
    }

    location / {
        proxy_pass [http://127.0.0.1:8001](http://127.0.0.1:8001);
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

```

---

## 5. Post-Launch Operational Checks
1. License & Trial Verification: Confirm InstallationLicense and trial/activation status in /licensing/ so active tenants aren't stuck in restricted mode.

2. No-Shell Tenant Onboarding: Log in as SUPER_ADMIN, open /tenants/setup-wizard/, provision a clinic or multi-branch hospital tenant, add branches, toggle required modules (CLINIC_OPD, PHARMACY, LABORATORY, IPD, BILLING), and create staff accounts.

3. Database Backups: Schedule automated daily dumps (pg_dump for PostgreSQL or mysqldump for MySQL) off-host and test restores periodically.


---

