"""Janela do receptor: aparelhos pareados, desparear e parear um aparelho novo (como no Options+)."""
from __future__ import annotations

from .client import ServiceUnavailable
from .hidpp.receiver import PAIR_TIMEOUT
from .i18n import T
from .qt import QtCore, QtWidgets

Qt = QtCore.Qt
W = QtWidgets

KIND_NAMES = {"unifying": "Receptor Unifying", "bolt": "Receptor Bolt", "other": "Receptor Logitech"}
DEVICE_KINDS = {"mouse": "Mouse", "keyboard": "Teclado", "trackball": "Trackball", "touchpad": "Touchpad",
                "presenter": "Apresentador", "numpad": "Teclado numérico", "remote": "Controle remoto",
                "headset": "Headset", "unknown": "Aparelho"}
ERRORS = {
    "timeout": "Nenhum aparelho apareceu a tempo. Tente de novo e não esqueça de desligar e ligar o aparelho "
               "depois que a luz piscar rápido.",
    "unsupported": "Este aparelho não é compatível com o receptor Unifying.",
    "full": "O receptor está cheio. Despareie um aparelho para liberar espaço.",
    "failed": "O receptor não aceitou o pedido. Tire e coloque o receptor de novo e tente outra vez.",
}


def receiver_title(r: dict) -> str:
    return T(KIND_NAMES.get(r["kind"], KIND_NAMES["other"]))


class ReceiverDialog(W.QDialog):
    def __init__(self, parent, client, receivers: list[dict]):
        super().__init__(parent)
        self.client = client
        self.receivers = receivers
        self.index = 0
        self.waiting = False       # nós abrimos o receptor e estamos esperando um aparelho
        self.deadline = 0.0
        self.setWindowTitle(T("Receptor"))
        self.resize(560, 520)
        lay = W.QVBoxLayout(self)
        lay.setSpacing(12)

        head = W.QHBoxLayout()
        self.title = W.QLabel(objectName="section")
        self.chooser = W.QComboBox()
        self.chooser.currentIndexChanged.connect(self._choose)
        head.addWidget(self.title, 1)
        head.addWidget(self.chooser)
        lay.addLayout(head)
        self.subtitle = W.QLabel(objectName="hint", wordWrap=True)
        lay.addWidget(self.subtitle)

        self.list_panel = W.QFrame(objectName="panel")
        self.rows = W.QVBoxLayout(self.list_panel)
        self.rows.setContentsMargins(16, 10, 16, 10)
        lay.addWidget(self.list_panel)

        # área do pareamento: instruções, contagem e resultado
        self.pair_panel = W.QFrame(objectName="panel")
        pair = W.QVBoxLayout(self.pair_panel)
        pair.setContentsMargins(16, 14, 16, 14)
        self.pair_text = W.QLabel(wordWrap=True)
        self.pair_text.setTextFormat(Qt.TextFormat.RichText)
        self.progress = W.QProgressBar(maximum=PAIR_TIMEOUT, textVisible=False, maximumHeight=6)
        self.progress.setStyleSheet("QProgressBar { background: #E5E7EB; border: none; border-radius: 3px; }"
                                    "QProgressBar::chunk { background: #2563EB; border-radius: 3px; }")
        buttons = W.QHBoxLayout()
        self.pair_btn = W.QPushButton(objectName="primary", clicked=self._start)
        self.cancel_btn = W.QPushButton(clicked=self._cancel)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.pair_btn)
        pair.addWidget(self.pair_text)
        pair.addWidget(self.progress)
        pair.addLayout(buttons)
        lay.addWidget(self.pair_panel)
        lay.addStretch(1)

        close = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        lay.addWidget(close)

        self.timer = QtCore.QTimer(self, interval=500, timeout=self._tick)
        client.receivers_changed.connect(self.update_receivers)
        self.update_receivers(receivers)

    # ------------------------------------------------------------ dados

    @property
    def receiver(self) -> dict | None:
        return self.receivers[self.index] if 0 <= self.index < len(self.receivers) else None

    def update_receivers(self, receivers: list[dict]):
        path = self.receiver["path"] if self.receiver else None
        self.receivers = receivers
        self.chooser.blockSignals(True)
        self.chooser.clear()
        for r in receivers:
            self.chooser.addItem(f"{receiver_title(r)} ({r['serial'] or r['product']})", r["path"])
        self.index = next((i for i, r in enumerate(receivers) if r["path"] == path), 0)
        self.chooser.setCurrentIndex(self.index)
        self.chooser.blockSignals(False)
        self.chooser.setVisible(len(receivers) > 1)
        self._show()

    def _choose(self, index):
        self.index = index
        self.waiting = False
        self._show()

    # ------------------------------------------------------------ desenho

    def _show(self):
        r = self.receiver
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().hide()   # some já; deleteLater só apaga no próximo ciclo
                item.widget().deleteLater()
        if r is None:
            self.title.setText(T("Receptor"))
            self.subtitle.setText(T("Nenhum receptor conectado. Coloque o receptor USB no computador."))
            self.list_panel.hide()
            self.pair_panel.hide()
            return
        self.list_panel.show()
        self.pair_panel.show()
        self.title.setText(receiver_title(r))
        used = len(r["devices"])
        self.subtitle.setText(T("Série {serial} · {used} de {slots} posições em uso",
                                serial=r["serial"] or "?", used=used, slots=r["slots"]))
        if not r["devices"]:
            self.rows.addWidget(W.QLabel(T("Nenhum aparelho pareado com este receptor."), objectName="hint"))
        for d in r["devices"]:
            self.rows.addWidget(self._row(r, d))
        self._show_pairing()

    def _row(self, r: dict, d: dict) -> W.QWidget:
        row = W.QWidget(objectName="rxrow")
        row.setStyleSheet("QWidget#rxrow { background: transparent; }")   # sem a faixa cinza do fundo
        lay = W.QHBoxLayout(row)
        lay.setContentsMargins(0, 6, 0, 6)
        text = W.QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(W.QLabel(d["name"], objectName="cardtitle"))
        text.addWidget(W.QLabel(T("{kind} · posição {slot}", kind=T(DEVICE_KINDS.get(d["kind"], "Aparelho")),
                                  slot=d["slot"]), objectName="hint"))
        lay.addLayout(text, 1)
        status = W.QLabel(T("Conectado") if d["online"] else T("Desligado"), objectName="battery")
        status.setProperty("offline", "false" if d["online"] else "true")
        lay.addWidget(status, alignment=Qt.AlignmentFlag.AlignVCenter)
        if r["can_pair"]:   # desparear usa o mesmo protocolo do pareamento (só Unifying por enquanto)
            unpair = W.QPushButton(T("Desparear"))
            unpair.clicked.connect(lambda _c=False, dev=d: self._unpair(r, dev))
            lay.addWidget(unpair, alignment=Qt.AlignmentFlag.AlignVCenter)
        return row

    def _show_pairing(self):
        r = self.receiver
        state = r["pairing"]
        self.pair_btn.setText(T("Parear novo aparelho"))
        self.cancel_btn.setText(T("Cancelar"))
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.pair_btn.setVisible(r["can_pair"])
        if not r["can_pair"]:
            self.waiting = False
            self.pair_text.setText(T("Parear pelo {receiver} ainda não está disponível no Mouse Options. Os "
                                     "aparelhos já pareados com ele funcionam normalmente.",
                                     receiver=receiver_title(r)))
            return
        if state["open"] or (self.waiting and not state["error"] and not state["new"]):
            self.pair_btn.setVisible(False)
            self.cancel_btn.setVisible(True)
            self.progress.setVisible(True)
            # o mesmo roteiro do Logi Options/Unifying Software: o aparelho só pede para parear ao ser ligado
            self.pair_text.setText(
                "<b>" + T("Esperando o aparelho…") + "</b><ol style='margin-left: -20px'>" +
                "<li>" + T("Com Easy-Switch: aperte o botão até acender o canal desejado e segure-o até a luz "
                           "piscar rápido.") + "</li>" +
                "<li>" + T("<b>Desligue e ligue o aparelho</b> pela chave liga/desliga.") + "</li></ol>" +
                T("Aparelhos sem Easy-Switch: só desligue e ligue."))
            if not self.timer.isActive():
                self.timer.start()
            return
        self.timer.stop()
        if self.waiting and state["new"]:
            name = next((d["name"] for d in r["devices"] if d["wpid"] == state["new"]), None) or T("Aparelho")
            self.pair_text.setText("<b>✓ " + T("{name} pareado!", name=name) + "</b><br>" +
                                   T("Ele já está pronto para usar e configurar no Mouse Options."))
            self.pair_btn.setText(T("Parear outro aparelho"))
        elif self.waiting and state["error"]:
            self.pair_text.setText("<b>" + T("Não deu para parear.") + "</b><br>" + T(ERRORS[state["error"]]))
            self.pair_btn.setText(T("Tentar de novo"))
        else:
            self.pair_text.setText(T("Para usar outro mouse ou teclado com este receptor, clique em Parear novo "
                                     "aparelho e siga os passos."))

    # ------------------------------------------------------------ ações

    def _start(self):
        r = self.receiver
        try:
            self.client.start_pairing(r["path"])
        except ServiceUnavailable as e:
            self.pair_text.setText(T("O serviço do Mouse Options não respondeu: {msg}", msg=str(e)))
            return
        self.waiting = True
        self.deadline = QtCore.QDateTime.currentSecsSinceEpoch() + PAIR_TIMEOUT
        r["pairing"] = {"open": False, "error": None, "new": None}   # até o receptor confirmar
        self.progress.setValue(PAIR_TIMEOUT)
        self._show_pairing()

    def _cancel(self):
        r = self.receiver
        self.waiting = False
        try:
            self.client.stop_pairing(r["path"])
        except ServiceUnavailable:
            pass
        r["pairing"]["open"] = False
        self._show_pairing()

    def _tick(self):
        left = max(0, self.deadline - QtCore.QDateTime.currentSecsSinceEpoch())
        self.progress.setValue(int(left))
        if left <= 0 and self.waiting and not self.receiver["pairing"]["open"]:
            self.receiver["pairing"]["error"] = "timeout"   # o receptor nunca confirmou a abertura
            self._show_pairing()

    def _unpair(self, r: dict, d: dict):
        q = T("Desparear {name} deste receptor? Para usar o aparelho com o receptor de novo, será preciso "
              "pareá-lo outra vez.", name=d["name"])
        if W.QMessageBox.question(self, T("Desparear"), q) != W.QMessageBox.StandardButton.Yes:
            return
        try:
            self.client.unpair(r["path"], d["slot"])
        except ServiceUnavailable as e:
            W.QMessageBox.warning(self, T("Desparear"), str(e))

    def done(self, result):  # noqa: D401 — fechar a janela com o receptor aberto: fecha o receptor
        r = self.receiver
        if r and (self.waiting or r["pairing"]["open"]):
            try:
                self.client.stop_pairing(r["path"])
            except ServiceUnavailable:
                pass
        self.timer.stop()
        super().done(result)
