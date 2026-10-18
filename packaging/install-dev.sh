#!/bin/bash
# Instala o serviço do Mouse Options para esta pessoa, rodando direto do código-fonte (desenvolvimento).
# Não precisa de sudo. Para desinstalar: ./install-dev.sh --remove
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DBUS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/dbus-1/services"
EXT_UUID=mouse-options@walbertfreitas.github.io
EXT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

# liga/desliga a extensão na configuração do GNOME (vale mesmo antes de o GNOME conhecê-la: no Wayland,
# extensões novas só são carregadas no próximo login)
extension_enabled() {
    python3 - "$1" "$EXT_UUID" <<'PY'
import sys
from gi.repository import Gio
s = Gio.Settings.new("org.gnome.shell")
on, uuid = sys.argv[1] == "on", sys.argv[2]
enabled = [u for u in s.get_strv("enabled-extensions") if u != uuid] + ([uuid] if on else [])
s.set_strv("enabled-extensions", enabled)
if on:
    s.set_strv("disabled-extensions", [u for u in s.get_strv("disabled-extensions") if u != uuid])
PY
}

if [ "${1:-}" = "--remove" ]; then
    systemctl --user disable --now mouse-optionsd.service 2>/dev/null || true
    rm -f "$UNIT_DIR/mouse-optionsd.service" "$DBUS_DIR/io.github.walbertfreitas.MouseOptions.service"
    extension_enabled off
    rm -f "$EXT_DIR/$EXT_UUID" "$APP_DIR/mouse-options.desktop" "$ICON_DIR/mouse-options.svg"
    systemctl --user daemon-reload
    echo "Serviço removido."
    exit 0
fi

mkdir -p "$UNIT_DIR" "$DBUS_DIR"
sed -e "s|^ExecStart=.*|ExecStart=/usr/bin/python3 -m mouse_options.daemon|" \
    -e "/^\[Service\]/a Environment=PYTHONPATH=$ROOT" \
    "$ROOT/packaging/mouse-optionsd.service" > "$UNIT_DIR/mouse-optionsd.service"
cp "$ROOT/packaging/io.github.walbertfreitas.MouseOptions.service" "$DBUS_DIR/"
systemctl --user daemon-reload
systemctl --user enable mouse-optionsd.service
python3 -c "import sys; sys.path.insert(0, '$ROOT'); from mouse_options import solaar_import as s; \
print('Solaar desligado.' if s.disable_solaar() else 'Solaar já estava desligado.')"
systemctl --user restart mouse-optionsd.service
mkdir -p "$EXT_DIR"
ln -sfn "$ROOT/extension/$EXT_UUID" "$EXT_DIR/$EXT_UUID"
extension_enabled on
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/mouse-options" && touch "${XDG_CONFIG_HOME:-$HOME/.config}/mouse-options/extension-enabled"
mkdir -p "$APP_DIR" "$ICON_DIR"
sed "s|^Exec=.*|Exec=env PYTHONPATH=$ROOT /usr/bin/python3 -m mouse_options|" \
    "$ROOT/packaging/mouse-options.desktop" > "$APP_DIR/mouse-options.desktop"
ln -sfn "$ROOT/mouse_options/icon.svg" "$ICON_DIR/mouse-options.svg"
echo "Serviço instalado e rodando: systemctl --user status mouse-optionsd"
echo "Atalho \"Mouse Options\" adicionado ao menu de aplicativos."
echo "Extensão do GNOME instalada e ativada (no Wayland, passa a valer no próximo login)."
