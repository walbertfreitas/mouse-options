"""Nomes no D-Bus do serviço (compartilhados com a interface sem carregar o serviço inteiro)."""
BUS_NAME = "io.github.walbertfreitas.MouseOptions"
OBJECT_PATH = "/io/github/walbertfreitas/MouseOptions"
INTERFACE = "io.github.walbertfreitas.MouseOptions1"

# Objeto exportado pela extensão do GNOME Shell (dentro do processo do gnome-shell)
SHELL_BUS_NAME = "org.gnome.Shell"
SHELL_PATH = "/io/github/walbertfreitas/MouseOptions/Shell"
SHELL_INTERFACE = "io.github.walbertfreitas.MouseOptions.Shell1"
EXTENSION_UUID = "mouse-options@walbertfreitas.github.io"
