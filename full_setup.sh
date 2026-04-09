#!/bin/bash
# Master Setup Script - Tüm kurulum için tek komut
# Kullanım: bash full_setup.sh [opsiyon]
# Opsiyonlar: quick | service | nginx

set -e

# Renkli çıktı
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}=========================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

print_header "Kargo Dağıtım Sistemi - Ubuntu Master Setup"

OPTION=${1:-interactive}
PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$PROJECT_DIR"

# Setup menüsü
if [ "$OPTION" = "interactive" ]; then
    echo "Lütfen kurulum tipini seçin:"
    echo ""
    echo "1) Hızlı Kurulum (venv + temel paketler)"
    echo "2) Service Kurulumu (backend + streamlit systemd)"
    echo "3) Tam Kurulum (backend + streamlit + nginx + SSL)"
    echo "4) Sadece Nginx (mevcut service'e proxy)"
    echo "0) Çıkış"
    echo ""
    read -p "Seçim (0-4): " OPTION
fi

case $OPTION in
    1|quick)
        print_header "AŞAMA 1: TEMEL KURULUM"
        
        print_info "Sistem paketleri güncelleniyor..."
        sudo apt-get update
        sudo apt-get install -y python3 python3-venv python3-pip git curl
        print_success "Sistem paketleri kuruldu"
        
        print_info "Sanal ortam oluşturuluyor..."
        if [ ! -d "venv" ]; then
            python3 -m venv venv
            print_success "Sanal ortam oluşturuldu"
        else
            print_info "Sanal ortam zaten var"
        fi
        
        print_info "Python paketleri kuruluyor..."
        source venv/bin/activate
        pip install --upgrade pip setuptools wheel
        pip install -r requirements.txt
        print_success "Python paketleri kuruldu"
        
        print_info "Gerekli klasörler oluşturuluyor..."
        mkdir -p yerelden_gelen/{normalized,processed}
        mkdir -p graph_cache cache
        mkdir -p yerelden_output/{single_job,jobs,vehicle_maps}
        mkdir -p logs
        print_success "Klasörler oluşturuldu"
        
        print_info "Scriptleri çalıştırılabilir yapılıyor..."
        chmod +x *.sh
        print_success "Scriptler hazır"
        
        echo ""
        print_success "Kurulum tamamlandı!"
        echo ""
        echo "Uygulamayı çalıştırmak için:"
        echo "  source venv/bin/activate"
        echo "  python3 -m streamlit run web_normalize.py --server.port 8501 --server.address 0.0.0.0"
        echo ""
        echo "Erişim adresi: http://localhost:8501"
        ;;
        
    2|service)
        print_header "AŞAMA 1-2: SERVICE KURULUMU"
        
        # Önce temel kurulum
        print_info "Sistem paketleri güncelleniyor..."
        sudo apt-get update
        sudo apt-get install -y python3 python3-venv python3-pip git curl
        
        print_info "Sanal ortam oluşturuluyor..."
        if [ ! -d "venv" ]; then
            python3 -m venv venv
        fi
        
        print_info "Python paketleri kuruluyor..."
        source venv/bin/activate
        pip install --upgrade pip setuptools wheel
        pip install -r requirements.txt
        
        mkdir -p yerelden_gelen/{normalized,processed}
        mkdir -p graph_cache cache
        mkdir -p yerelden_output/{single_job,jobs,vehicle_maps}
        mkdir -p logs
        chmod +x *.sh
        print_success "Temel kurulum tamamlandı"
        
        # Service kurulumu
        print_info "Systemd service'leri kuruluyor..."
        sudo cp kargo-api.service /etc/systemd/system/
        sudo cp kargo-streamlit.service /etc/systemd/system/
        sudo systemctl daemon-reload
        sudo systemctl enable kargo-api
        sudo systemctl enable kargo-streamlit
        sudo systemctl start kargo-api
        sudo systemctl start kargo-streamlit
        sleep 2

        if sudo systemctl is-active --quiet kargo-api; then
            print_success "Backend service başarıyla başladı"
        else
            print_error "Backend service başlama başarısız"
        fi
        
        if sudo systemctl is-active --quiet kargo-streamlit; then
            print_success "Streamlit service başarıyla başladı"
        else
            print_error "Streamlit service başlama başarısız"
        fi
        
        echo ""
        print_success "Service Kurulumu Tamamlandı!"
        echo ""
        echo "Service komutları:"
        echo "  sudo systemctl start kargo-api          # Backend başlat"
        echo "  sudo systemctl restart kargo-api        # Backend yeniden başlat"
        echo "  sudo journalctl -u kargo-api -f         # Backend logları"
        echo "  sudo systemctl start kargo-streamlit    # Başlat"
        echo "  sudo systemctl stop kargo-streamlit     # Durdur"
        echo "  sudo systemctl restart kargo-streamlit  # Yeniden başlat"
        echo "  sudo systemctl status kargo-streamlit   # Durum"
        echo "  sudo journalctl -u kargo-streamlit -f   # Loglar"
        echo ""
        echo "Erişim adresi: http://localhost:8501"
        ;;
        
    3|full)
        print_header "AŞAMA 1-3: TAM KURULUM"
        
        # Temel kurulum
        print_info "Sistem paketleri güncelleniyor..."
        sudo apt-get update
        sudo apt-get install -y python3 python3-venv python3-pip git curl
        
        print_info "Sanal ortam oluşturuluyor..."
        if [ ! -d "venv" ]; then
            python3 -m venv venv
        fi
        
        print_info "Python paketleri kuruluyor..."
        source venv/bin/activate
        pip install --upgrade pip setuptools wheel
        pip install -r requirements.txt
        
        mkdir -p yerelden_gelen/{normalized,processed}
        mkdir -p graph_cache cache
        mkdir -p yerelden_output/{single_job,jobs,vehicle_maps}
        mkdir -p logs
        chmod +x *.sh
        print_success "Temel kurulum tamamlandı"
        
        # Service kurulumu
        print_info "Systemd service'leri kuruluyor..."
        sudo cp kargo-api.service /etc/systemd/system/
        sudo cp kargo-streamlit.service /etc/systemd/system/
        sudo systemctl daemon-reload
        sudo systemctl enable kargo-api
        sudo systemctl enable kargo-streamlit
        sudo systemctl start kargo-api
        sudo systemctl start kargo-streamlit
        sleep 2
        print_success "Service kurulumu tamamlandı"
        
        # Nginx kurulumu
        print_info "Nginx reverse proxy kuruluyor..."
        read -p "Domain adınız: " DOMAIN
        
        if bash setup_nginx.sh "$DOMAIN"; then
            print_success "Nginx kurulumu tamamlandı"
        else
            print_error "Nginx kurulumu başarısız oldu"
        fi
        
        echo ""
        print_success "TAM Kurulum Tamamlandı!"
        echo ""
        echo "Service komutları:"
        echo "  sudo systemctl status kargo-api"
        echo "  sudo journalctl -u kargo-api -f"
        echo "  sudo systemctl status kargo-streamlit"
        echo "  sudo journalctl -u kargo-streamlit -f"
        echo ""
        echo "Nginx komutları:"
        echo "  sudo systemctl status nginx"
        echo "  sudo systemctl reload nginx"
        echo ""
        echo "Erişim adresi: https://$DOMAIN"
        ;;
        
    4|nginx)
        print_header "NGINX REVERSE PROXY KURULUMU"
        
        read -p "Domain adınız: " DOMAIN
        
        if bash setup_nginx.sh "$DOMAIN"; then
            print_success "Nginx kurulumu tamamlandı"
            echo ""
            echo "Erişim adresi: https://$DOMAIN"
        else
            print_error "Nginx kurulumu başarısız"
        fi
        ;;
        
    0)
        print_info "Çıkılıyor..."
        exit 0
        ;;
        
    *)
        print_error "Geçersiz seçim"
        exit 1
        ;;
esac

echo ""
print_info "Daha fazla bilgi için README_UBUNTU_SETUP.md dosyasını kontrol edin"
echo ""
