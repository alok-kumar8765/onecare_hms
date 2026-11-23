python backend/manage.py check --settings=config.settings.dev
python backend/manage.py makemigrations --check --dry-run --settings=config.settings.dev


MIGRATIONS : python backend/manage.py makemigrations core accounts tenants --settings=config.settings.dev
MIGRTAE : python backend/manage.py migrate --settings=config.settings.dev
SUPER USER : python backend/manage.py createsuperuser --settings=config.settings.dev
RUN SERVER : python backend/manage.py runserver --settings=config.settings.dev


python manage.py makemigrations --settings=config.settings.prod
python manage.py migrate --settings=config.settings.prod
python manage.py collectstatic --noinput --settings=config.settings.prod
python manage.py check --deploy --settings=config.settings.prod