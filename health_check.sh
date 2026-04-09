#!/bin/bash
# Sağlık kontrol scripti - Sistem ve servislerin sağlığını kontrol eder

PROJECT_DIR="${1:-.}"
LOG_FILE="$PROJECT_DIR/logs/health_check.log"

# Log fonksiyonu
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Alert fonksiyonu
alert() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ALERT: $1" | tee -a "$LOG_FILE"
}

mkdir -p "$PROJECT_DIR/logs"

log "🔍 Sağlık kontrolü başlıyor..."

# 1. Streamlit Service
log "Streamlit Service kontrol ediliyor..."
if sudo systemctl is-active --quiet kargo-streamlit; then
    log "✓ Streamlit Service çalışıyor"
else
    alert "Streamlit Service çalışmıyor!"
    sudo systemctl start kargo-streamlit
fi

# 2. Port kontrol
log "Port 8501 kontrol ediliyor..."
if sudo ss -tlnp 2>/dev/null | grep -q :8501; then
    log "✓ Port 8501 açık"
else
    alert "Port 8501 kapalı!"
fi

# 3. Disk alanı
log "Disk alanı kontrol ediliyor..."
DISK_USAGE=$(df "$PROJECT_DIR" | tail -1 | awk '{print int($5)}')
if [ "$DISK_USAGE" -gt 90 ]; then
    alert "Disk kullanımı %$DISK_USAGE (Kritik!)"
elif [ "$DISK_USAGE" -gt 80 ]; then
    alert "Disk kullanımı %$DISK_USAGE (Uyarı)"
else
    log "✓ Disk kullanımı %$DISK_USAGE (Normal)"
fi

# 4. Bellek
log "Bellek kontrol ediliyor..."
MEM_USAGE=$(free | grep Mem | awk '{printf("%.0f\n", $3/$2 * 100)}')
if [ "$MEM_USAGE" -gt 90 ]; then
    alert "Bellek kullanımı %$MEM_USAGE (Kritik!)"
elif [ "$MEM_USAGE" -gt 80 ]; then
    alert "Bellek kullanımı %$MEM_USAGE (Uyarı)"
else
    log "✓ Bellek kullanımı %$MEM_USAGE (Normal)"
fi

# 5. Nginx (eğer kuruluysa)
if sudo systemctl is-enabled nginx 2>/dev/null; then
    log "Nginx kontrol ediliyor..."
    if sudo systemctl is-active --quiet nginx; then
        log "✓ Nginx çalışıyor"
    else
        alert "Nginx çalışmıyor!"
        sudo systemctl start nginx
    fi
fi

# 6. Dosya izinleri
log "Dosya izinleri kontrol ediliyor..."
if [ -w "$PROJECT_DIR/yerelden_gelen" ]; then
    log "✓ Yazma izinleri OK"
else
    alert "Yazma izinleri hata!"
fi

log "✅ Sağlık kontrolü tamamlandı"
echo ""
