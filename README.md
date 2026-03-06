# Django Cash Flow Projection

Connects to Odoo 17/18 via REST API to display AR and AP lines
as a cash flow projection — with web dashboard, JSON API, Excel, and PDF export.

## Project Structure

```
cashflow_project/
├── manage.py
├── requirements.txt
├── cashflow_project/
│   ├── settings.py       ← Odoo connection config here
│   └── urls.py
└── cashflow/
    ├── odoo_client.py    ← Odoo REST API wrapper
    ├── services.py       ← Cashflow projection logic
    ├── views.py          ← Dashboard, API, Excel, PDF
    ├── urls.py
    └── templates/cashflow/dashboard.html
```

# CashFlow THB

Cash flow projection dashboard that pulls live AR/AP data from Odoo 17/18.

---

## Droplet Deployment (Ubuntu 22.04)

### 1. Install system packages

```bash
sudo apt update && sudo apt install -y python3-pip python3-venv nginx
```

### 2. Clone / upload the project

```bash
cd /var/www
git clone <your-repo> cashflow
# — or — scp/rsync the project folder here
cd cashflow
```

### 3. Create virtualenv & install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
nano .env          # fill in SECRET_KEY, ALLOWED_HOSTS, ODOO_* values
```

### 5. Initialise the database & collect static files

```bash
source venv/bin/activate
python manage.py migrate
python manage.py createsuperuser      # create your first admin user
python manage.py collectstatic --noinput
```

Static files are written to `staticfiles/` — nginx will serve them directly.

### 6. Gunicorn systemd service

Create `/etc/systemd/system/cashflow.service`:

```ini
[Unit]
Description=CashFlow THB — Gunicorn
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/cashflow
EnvironmentFile=/var/www/cashflow/.env
ExecStart=/var/www/cashflow/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/run/cashflow.sock \
    cashflow_project.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cashflow
sudo systemctl start cashflow
sudo systemctl status cashflow
```

### 7. Nginx configuration

Create `/etc/nginx/sites-available/cashflow`:

```nginx
server {
    listen 80;
    server_name your-droplet-ip yourdomain.com;

    # Static files served directly by nginx
    location /static/ {
        alias /var/www/cashflow/staticfiles/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # Everything else goes to Gunicorn
    location / {
        proxy_pass         http://unix:/run/cashflow.sock;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/cashflow /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 8. (Optional) HTTPS with Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

---

## Managing users

There is no self-signup. Create users via the Django admin panel at `/admin/`.
Log in with your superuser, go to **Users → Add User**.

---

## Environment variables reference

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key (generate a fresh one) |
| `DEBUG` | | `False` in production (default) |
| `ALLOWED_HOSTS` | ✅ | Comma-separated IPs/domains |
| `ODOO_URL` | ✅ | Odoo domain root — no `/odoo` suffix |
| `ODOO_DB` | ✅ | Odoo database name |
| `ODOO_USERNAME` | ✅ | Odoo login email |
| `ODOO_PASSWORD` | ✅ | Odoo password or API key |
| `ODOO_CACHE_TIMEOUT` | | Seconds to cache Odoo data (default `300`) |

---

## Useful commands

```bash
source /var/www/cashflow/venv/bin/activate  # activate venv
sudo journalctl -u cashflow -f              # live logs
sudo systemctl restart cashflow             # restart after code changes
python manage.py collectstatic --noinput    # after static/template changes
```