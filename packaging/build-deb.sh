#!/bin/bash
# Gera o pacote .deb do Mouse Options (arquitetura "all": só Python, usa as bibliotecas do sistema).
# Uso: packaging/build-deb.sh   → dist/mouse-options_<versão>_all.deb
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(cat "$ROOT/VERSION")"
PKG=mouse-options
BUILD="$(mktemp -d)"
STAGE="$BUILD/${PKG}_${VERSION}_all"
trap 'rm -rf "$BUILD"' EXIT

# Código Python (interface, serviço e camada HID++)
for dir in mouse_options mouse_options/daemon mouse_options/hidpp; do
    install -d "$STAGE/usr/lib/$PKG/$dir"
    install -m 644 "$ROOT"/$dir/*.py "$STAGE/usr/lib/$PKG/$dir/"
done
install -m 644 "$ROOT/mouse_options/icon.svg" "$STAGE/usr/lib/$PKG/mouse_options/"
install -d "$STAGE/usr/lib/$PKG/mouse_options/images"
install -m 644 "$ROOT"/mouse_options/images/*.png "$STAGE/usr/lib/$PKG/mouse_options/images/"

# Comandos: a interface e o serviço
install -d "$STAGE/usr/bin"
for cmd in "$PKG:mouse_options" "mouse-optionsd:mouse_options.daemon"; do
    printf '#!/bin/sh\nPYTHONPATH=/usr/lib/%s${PYTHONPATH:+:$PYTHONPATH} exec /usr/bin/python3 -m %s "$@"\n' \
        "$PKG" "${cmd#*:}" > "$STAGE/usr/bin/${cmd%%:*}"
    chmod 755 "$STAGE/usr/bin/${cmd%%:*}"
done

# Serviço da sessão: inicia com o login (systemd) ou quando a interface chama (D-Bus)
install -D -m 644 "$ROOT/packaging/mouse-optionsd.service" "$STAGE/usr/lib/systemd/user/mouse-optionsd.service"
install -d "$STAGE/usr/lib/systemd/user/graphical-session.target.wants"
ln -s ../mouse-optionsd.service "$STAGE/usr/lib/systemd/user/graphical-session.target.wants/mouse-optionsd.service"
install -D -m 644 "$ROOT/packaging/io.github.walbertfreitas.MouseOptions.service" \
    "$STAGE/usr/share/dbus-1/services/io.github.walbertfreitas.MouseOptions.service"

# Extensão do GNOME Shell (app em foco no Wayland, balões nativos, ações de janela)
EXT="$STAGE/usr/share/gnome-shell/extensions/mouse-options@walbertfreitas.github.io"
install -d "$EXT"
install -m 644 "$ROOT"/extension/mouse-options@walbertfreitas.github.io/*.js \
    "$ROOT"/extension/mouse-options@walbertfreitas.github.io/metadata.json "$EXT/"

# Reparo automático do cache do Bluetooth (serviço do sistema, roda como root)
install -D -m 755 "$ROOT/packaging/bt-repair.py" "$STAGE/usr/libexec/$PKG/bt-repair"
install -D -m 644 "$ROOT/packaging/mouse-options-bt-repair.service" \
    "$STAGE/usr/lib/systemd/system/mouse-options-bt-repair.service"

# Permissão para a pessoa logada acessar os aparelhos Logitech e o uinput
install -D -m 644 "$ROOT/packaging/70-mouse-options.rules" "$STAGE/usr/lib/udev/rules.d/70-mouse-options.rules"

# Menu e ícone
install -D -m 644 "$ROOT/packaging/$PKG.desktop" "$STAGE/usr/share/applications/$PKG.desktop"
install -D -m 644 "$ROOT/mouse_options/icon.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/$PKG.svg"

# Documentação
DOC="$STAGE/usr/share/doc/$PKG"
install -D -m 644 "$ROOT/packaging/copyright" "$DOC/copyright"
gzip -9n -c "$ROOT/packaging/changelog" > "$DOC/changelog.gz"
chmod 644 "$DOC/changelog.gz"

# Metadados
install -d "$STAGE/DEBIAN"
SIZE=$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@SIZE@/$SIZE/" "$ROOT/packaging/control.in" > "$STAGE/DEBIAN/control"
install -m 755 "$ROOT/packaging/postinst" "$STAGE/DEBIAN/postinst"
install -m 755 "$ROOT/packaging/prerm" "$STAGE/DEBIAN/prerm"

# Remove caches de Python que possam ter vindo junto
find "$STAGE" -name '__pycache__' -prune -exec rm -rf {} +

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$STAGE" "$ROOT/dist/" >/dev/null
echo "Pacote gerado: $ROOT/dist/${PKG}_${VERSION}_all.deb"
