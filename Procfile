web: gunicorn cinema_project.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 60
release: bash -c "python manage.py migrate --noinput && python manage.py ensure_admin && python manage.py seed_demo"
