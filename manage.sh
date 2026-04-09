#!/bin/bash
# Kargo Dağıtım Sistemi - Yönetim Kontrol Paneli
# Tüm servisleri ve sistemi yönetmek için

set -e

# Renkli çıktı
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    clear
    echo -e "${BLUE}╔═══════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║ Kargo Dağıtım Sistemi - Yönetim Paneli   ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════╝${NC}"
    echo ""
}

show_status() {
    echo -e "${YELLOW}📊 Sistem Durumu${NC}"
    echo "─────────────────────────────────────"
    
    # Streamlit
    if sudo systemctl is-active --quiet kargo-streamlit; then
        echo -e "${GREEN}✓${NC} Streamlit Service: ÇALIŞIYOR"
    else
        echo -e "${RED}✗${NC} Streamlit Service: DURDURULMUŞ"
    fi

    # Backend
    if sudo systemctl is-active --quiet kargo-api; then
        echo -e "${GREEN}✓${NC} Backend API: ÇALIŞIYOR"
    else
        echo -e "${RED}✗${NC} Backend API: DURDURULMUŞ"
    fi
    
    # Nginx
    if sudo systemctl is-active --quiet nginx 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Nginx: ÇALIŞIYOR"
    else
        echo -e "${YELLOW}○${NC} Nginx: YÜKLÜ DEĞİL/DURDURULMUŞ"
    fi
    
    # Port kontrol
    if sudo ss -tlnp 2>/dev/null | grep -q :8501; then
        echo -e "${GREEN}✓${NC} Port 8501: AÇIK"
    else
        echo -e "${RED}✗${NC} Port 8501: KAPAL"
    fi

    if sudo ss -tlnp 2>/dev/null | grep -q :8010; then
        echo -e "${GREEN}✓${NC} Port 8010: AÇIK"
    else
        echo -e "${RED}✗${NC} Port 8010: KAPAL"
    fi
    
    # Disk alanı
    DISK_USAGE=$(df -h ~ | tail -1 | awk '{print $5}')
    echo -e "${YELLOW}💾${NC} Disk Kullanımı: $DISK_USAGE"
    
    # Bellek
    MEM_USAGE=$(free -h | grep Mem | awk '{print $3"/"$2}')
    echo -e "${YELLOW}🧠${NC} Bellek: $MEM_USAGE"
    
    echo ""
}

menu() {
    print_header
    show_status
    
    echo -e "${BLUE}📋 Menu${NC}"
    echo "─────────────────────────────────────"
    echo "1) Streamlit Service Başlat"
    echo "2) Streamlit Service Durdur"
    echo "3) Streamlit Service Yeniden Başlat"
    echo "4) Service Durumu"
    echo "5) Livelogları İzle"
    echo ""
    echo "6) Nginx Yeniden Başlat"
    echo "7) Nginx Konfigürasyonu Test Et"
    echo ""
    echo "8) Sistem Bilgisini Göster"
    echo "9) Logları Temizle"
    echo ""
    echo "0) Çıkış"
    echo ""
    read -p "Seçim: " choice
    
    case $choice in
        1)
            echo ""
            echo "Streamlit başlatılıyor..."
            sudo systemctl start kargo-streamlit
            sleep 2
            if sudo systemctl is-active --quiet kargo-streamlit; then
                echo -e "${GREEN}✓ Başarıyla başlatıldı${NC}"
            else
                echo -e "${RED}✗ Başlatılamadı${NC}"
            fi
            read -p "Devam etmek için Enter tuşuna bas..."
            menu
            ;;
            
        2)
            echo ""
            echo "Streamlit durduruluyoz..."
            sudo systemctl stop kargo-streamlit
            sleep 1
            echo -e "${GREEN}✓ Durduruldu${NC}"
            read -p "Devam etmek için Enter tuşuna bas..."
            menu
            ;;
            
        3)
            echo ""
            echo "Streamlit yeniden başlatılıyor..."
            sudo systemctl restart kargo-streamlit
            sleep 2
            if sudo systemctl is-active --quiet kargo-streamlit; then
                echo -e "${GREEN}✓ Başarıyla yeniden başlatıldı${NC}"
            else
                echo -e "${RED}✗ Yeniden başlatılamadı${NC}"
            fi
            read -p "Devam etmek için Enter tuşuna bas..."
            menu
            ;;
            
        4)
            clear
            echo -e "${BLUE}Streamlit Service Durumu${NC}"
            echo "─────────────────────────────────────"
            sudo systemctl status kargo-streamlit
            echo ""
            read -p "Devam etmek için Enter tuşuna bas..."
            menu
            ;;
            
        5)
            clear
            echo -e "${BLUE}Livelogları İzle (Çıkış: Ctrl+C)${NC}"
            echo "─────────────────────────────────────"
            sudo journalctl -u kargo-streamlit -f
            menu
            ;;
            
        6)
            echo ""
            echo "Nginx yeniden başlatılıyor..."
            sudo systemctl restart nginx
            sleep 1
            if sudo systemctl is-active --quiet nginx 2>/dev/null; then
                echo -e "${GREEN}✓ Nginx yeniden başlatıldı${NC}"
            else
                echo -e "${RED}✗ Nginx başlatılamadı${NC}"
            fi
            read -p "Devam etmek için Enter tuşuna bas..."
            menu
            ;;
            
        7)
            clear
            echo -e "${BLUE}Nginx Konfigürasyonu Test${NC}"
            echo "─────────────────────────────────────"
            if sudo nginx -t; then
                echo -e "${GREEN}✓ Konfigürasyon geçerli${NC}"
            else
                echo -e "${RED}✗ Konfigürasyon hatası${NC}"
            fi
            echo ""
            read -p "Devam etmek için Enter tuşuna bas..."
            menu
            ;;
            
        8)
            clear
            echo -e "${BLUE}Sistem Bilgisi${NC}"
            echo "─────────────────────────────────────"
            echo "Hostname: $(hostname)"
            echo "Sistem: $(uname -s)"
            echo "Kernel: $(uname -r)"
            echo "IP Adresi: $(hostname -I)"
            echo ""
            echo "CPU Bilgisi:"
            nproc --all
            echo "çekirdek"
            echo ""
            echo "Bellek Bilgisi:"
            free -h
            echo ""
            echo "Disk Bilgisi:"
            df -h ~ | tail -1
            echo ""
            echo "Python Versiyonu:"
            python3 --version
            echo ""
            echo "Streamlit Process:"
            ps aux | grep streamlit | grep -v grep || echo "Çalışmıyor"
            echo ""
            read -p "Devam etmek için Enter tuşuna bas..."
            menu
            ;;
            
        9)
            echo ""
            read -p "Logları gerçekten temizlemek istiyor musunuz? (y/n): " confirm
            if [ "$confirm" = "y" ]; then
                sudo journalctl --vacuum-time=1d
                echo -e "${GREEN}✓ 1 günden eski loglar silindi${NC}"
            else
                echo "İptal edildi"
            fi
            read -p "Devam etmek için Enter tuşuna bas..."
            menu
            ;;
            
        0)
            echo ""
            echo "Çıkılıyor..."
            exit 0
            ;;
            
        *)
            echo -e "${RED}Geçersiz seçim${NC}"
            sleep 1
            menu
            ;;
    esac
}

# Main
if [ "$EUID" -ne 0 ] && ! sudo -n true 2>/dev/null; then
    echo -e "${RED}Bu script sudo izinleri gerektirir${NC}"
    echo "Lütfen şu komutu çalıştırın: sudo bash $0"
    exit 1
fi

menu
