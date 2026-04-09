#!/bin/bash
# Kargo Dağıtım Sistemi - Nginx Reverse Proxy Kurulumu
# HTTPS/SSL desteği ile Streamlit'i expose etme

set -e

DOMAIN=${1:-}
PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
NGINX_SITE_NAME="kargo-dagitim"
LETSENCRYPT_EMAIL=${LETSENCRYPT_EMAIL:-webmaster@$DOMAIN}

if [ -z "$DOMAIN" ]; then
    echo "Kullanım: bash setup_nginx.sh your.domain.com"
    echo ""
    echo "Örnek: bash setup_nginx.sh kargo.example.com"
    exit 1
fi

echo "=========================================="
echo "Nginx Reverse Proxy Kurulumu"
echo "=========================================="
echo "Domain: $DOMAIN"
echo "Proje dizini: $PROJECT_DIR"
echo ""

# 1. Nginx kur
echo "[1/4] Nginx kuruluyor..."
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx

# 2. HTTP config oluştur ve ACME challenge aç
echo "[2/4] Nginx HTTP konfigürasyonu yazılıyor..."
sudo mkdir -p /var/www/certbot
sudo tee "/etc/nginx/sites-available/$NGINX_SITE_NAME" > /dev/null <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    client_max_body_size 100m;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
EOF

# 3. Nginx konfigürasyonunu aktive et ve challenge erişimini aç
echo "[3/4] Nginx konfigürasyonu aktive ediliyor..."
sudo ln -sf "/etc/nginx/sites-available/$NGINX_SITE_NAME" "/etc/nginx/sites-enabled/$NGINX_SITE_NAME"
sudo rm -f /etc/nginx/sites-enabled/default
if sudo nginx -t; then
    echo "✓ Nginx config test başarılı"
else
    echo "✗ Nginx config hatası"
    exit 1
fi
sudo systemctl enable nginx
sudo systemctl reload nginx

# 4. SSL sertifikasını al/yenile ve final HTTPS config yaz
echo "[4/4] Let's Encrypt sertifikası alınıyor/yenileniyor..."
sudo certbot certonly \
    --webroot \
    -w /var/www/certbot \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --keep-until-expiring \
    --email "$LETSENCRYPT_EMAIL"

sudo tee "/etc/nginx/sites-available/$NGINX_SITE_NAME" > /dev/null <<EOF
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    '' close;
}

upstream streamlit_app {
    server 127.0.0.1:8501;
    keepalive 32;
}

server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    client_max_body_size 100m;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_session_tickets off;

    client_max_body_size 100m;

    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection \$connection_upgrade;
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 60s;

    location / {
        proxy_pass http://streamlit_app;
    }

    access_log /var/log/nginx/kargo-access.log;
    error_log /var/log/nginx/kargo-error.log;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
}
EOF

sudo nginx -t
sudo systemctl restart nginx

echo ""
echo "=========================================="
echo "Nginx Kurulumu Tamamlandı!"
echo "=========================================="
echo ""
echo "Erişim adresi: https://$DOMAIN"
echo ""
echo "Servisleri kontrol edin:"
echo "  sudo systemctl status kargo-api"
echo "  sudo systemctl status kargo-streamlit"
echo ""
echo "Sertifika yenileme testi:"
echo "  sudo certbot renew --dry-run"
echo ""
echo "Nginx loglarını izlemek için:"
echo "  sudo tail -f /var/log/nginx/kargo-access.log"
echo "  sudo tail -f /var/log/nginx/kargo-error.log"
echo ""
