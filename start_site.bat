@echo off
title Kino Aurora - local server
cd /d "D:\Методология\cinema_project"
echo ==========================================
echo  Kino Aurora:  http://127.0.0.1:8000/admin/
echo  Account: admin / admin12345
echo  Ctrl+C to stop server
echo ==========================================
python manage.py runserver
pause