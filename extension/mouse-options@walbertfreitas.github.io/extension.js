// Mouse Options — extensão do GNOME Shell (GPL-3.0-or-later)
//
// Roda dentro do GNOME Shell e faz o que nenhum programa comum pode fazer no Wayland:
//  - informa ao serviço mouse-optionsd qual app está em foco (perfis por aplicativo);
//  - volume, mudo e brilho com os balões nativos do GNOME;
//  - ações de janela e de área de trabalho direto no gerenciador de janelas.
// O serviço chama Action(nome) no objeto exportado aqui; se a extensão estiver desligada, ele usa outro caminho.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gvc from 'gi://Gvc';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Volume from 'resource:///org/gnome/shell/ui/status/volume.js';

const SERVICE = 'io.github.walbertfreitas.MouseOptions';
const SERVICE_PATH = '/io/github/walbertfreitas/MouseOptions';
const SERVICE_IFACE = 'io.github.walbertfreitas.MouseOptions1';
const SHELL_PATH = '/io/github/walbertfreitas/MouseOptions/Shell';
const SHELL_IFACE = `
<node>
  <interface name="io.github.walbertfreitas.MouseOptions.Shell1">
    <method name="Action">
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="handled" direction="out"/>
    </method>
    <method name="ListWindows">
      <arg type="s" name="windows" direction="out"/>
    </method>
    <property name="Version" type="u" access="read"/>
  </interface>
</node>`;

const VOLUME_ICONS = ['audio-volume-muted-symbolic', 'audio-volume-low-symbolic',
    'audio-volume-medium-symbolic', 'audio-volume-high-symbolic', 'audio-volume-overamplified-symbolic'];

function readComm(pid) {
    try {
        const [ok, bytes] = GLib.file_get_contents(`/proc/${pid}/comm`);
        return ok ? new TextDecoder().decode(bytes).trim() : null;
    } catch {
        return null;
    }
}

class ShellActions {
    constructor() {
        this._tracker = Shell.WindowTracker.get_default();
        this._soundSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.sound'});
        this._mediaKeys = new Gio.Settings({schema_id: 'org.gnome.settings-daemon.plugins.media-keys'});
        this._minimizedForDesktop = [];
    }

    get Version() {
        return 1;
    }

    Action(name) {
        const action = this[`_${name}`];
        if (typeof action !== 'function')
            return false;
        try {
            return action.call(this) !== false;
        } catch (e) {
            logError(e, `Mouse Options: ação ${name}`);
            return false;
        }
    }

    ListWindows() {
        // só o identificador e o nome do app (títulos de janela podem ter dados pessoais)
        const seen = new Map();
        for (const actor of global.get_window_actors()) {
            const w = actor.meta_window;
            if (w.skip_taskbar || w.get_window_type() !== Meta.WindowType.NORMAL)
                continue;
            const ident = w.get_wm_class_instance() || w.get_wm_class() || w.get_gtk_application_id();
            if (!ident || seen.has(ident))
                continue;
            const app = this._tracker.get_window_app(w);
            seen.set(ident, app ? app.get_name() : (w.get_wm_class() || ident));
        }
        return JSON.stringify([...seen.entries()]);
    }

    // ------------------------------------------------------------ volume e brilho

    get _mixer() {
        return Volume.getMixerControl();
    }

    _volumeOsd(stream, muted = stream.is_muted) {
        const control = this._mixer;
        const norm = control.get_vol_max_norm();
        const amplified = this._soundSettings.get_boolean('allow-volume-above-100-percent');
        const maxLevel = amplified ? control.get_vol_max_amplified() / norm : 1;
        const level = muted ? 0 : stream.volume / norm;
        let n = 0;
        if (!muted && stream.volume > 0)
            n = level > 1 ? 4 : Math.min(3, Math.max(1, Math.ceil(level * 3)));
        Main.osdWindowManager.show(-1, Gio.ThemedIcon.new(VOLUME_ICONS[n]), null, level, maxLevel);
    }

    _changeVolume(direction) {
        const control = this._mixer;
        const sink = control.get_default_sink();
        if (!sink)
            return false;
        const norm = control.get_vol_max_norm();
        const amplified = this._soundSettings.get_boolean('allow-volume-above-100-percent');
        const max = amplified ? control.get_vol_max_amplified() : norm;
        const step = this._mediaKeys.get_int('volume-step') / 100 * norm;
        let muted = sink.is_muted;
        if (this._lastMute && this._lastMute.stream === sink &&
            GLib.get_monotonic_time() - this._lastMute.time < 1500000)
            muted = this._lastMute.muted;
        if (direction > 0 && muted) {
            sink.change_is_muted(false);
            this._lastMute = {stream: sink, muted: false, time: GLib.get_monotonic_time()};
            muted = false;
        }
        sink.volume = Math.max(0, Math.min(max, sink.volume + direction * step));
        sink.push_volume();
        this._volumeOsd(sink, muted);
        // como o GNOME: o "plim" só toca se nada estiver tocando
        if (sink.state !== Gvc.MixerStreamState.RUNNING && this._soundSettings.get_boolean('event-sounds'))
            global.display.get_sound_player().play_from_theme('audio-volume-change', 'Volume changed', null);
        return true;
    }

    _volume_up() {
        return this._changeVolume(1);
    }

    _volume_down() {
        return this._changeVolume(-1);
    }

    _toggleMuted(stream) {
        // o novo estado demora um instante para aparecer em is_muted: dois apertos rápidos não podem
        // ler o valor antigo e repetir o mesmo pedido
        const recent = this._lastMute && this._lastMute.stream === stream &&
            GLib.get_monotonic_time() - this._lastMute.time < 1500000;
        const muted = !(recent ? this._lastMute.muted : stream.is_muted);
        stream.change_is_muted(muted);
        this._lastMute = {stream, muted, time: GLib.get_monotonic_time()};
        return muted;
    }

    _mute() {
        const sink = this._mixer.get_default_sink();
        if (!sink)
            return false;
        const muted = this._toggleMuted(sink);
        this._volumeOsd(sink, muted);
        return true;
    }

    _mic_mute() {
        const source = this._mixer.get_default_source();
        if (!source)
            return false;
        const muted = this._toggleMuted(source);
        const icon = muted ? 'microphone-sensitivity-muted-symbolic' : 'microphone-sensitivity-high-symbolic';
        Main.osdWindowManager.show(-1, Gio.ThemedIcon.new(icon), null, null, null);
        return true;
    }

    _brightness(method) {
        Gio.DBus.session.call('org.gnome.SettingsDaemon.Power', '/org/gnome/SettingsDaemon/Power',
            'org.gnome.SettingsDaemon.Power.Screen', method, null, null, Gio.DBusCallFlags.NONE, 2000, null,
            (conn, res) => {
                try {
                    const [percent] = conn.call_finish(res).deepUnpack();
                    if (percent >= 0) {
                        Main.osdWindowManager.show(-1, Gio.ThemedIcon.new('display-brightness-symbolic'), null,
                            percent / 100, 1);
                    }
                } catch (e) {
                    logError(e, 'Mouse Options: brilho');
                }
            });
        return true;
    }

    _brightness_up() {
        return this._brightness('StepUp');
    }

    _brightness_down() {
        return this._brightness('StepDown');
    }

    // ------------------------------------------------------------ visão geral, apps, captura

    _overview() {
        if (Main.overview.visible)
            Main.overview.hide();
        else
            Main.overview.show();   // a visão das janelas (o toggle pode ter sido trocado por outra extensão)
    }

    _app_grid() {
        if (Main.overview.visible)
            Main.overview.hide();
        else
            Main.overview.showApps();
    }

    _screenshot() {
        Main.screenshotUI.open().catch(e => logError(e, 'Mouse Options: captura'));
    }

    // ------------------------------------------------------------ janelas

    get _focused() {
        return global.display.focus_window;
    }

    _maximize() {
        const w = this._focused;
        if (!w || !w.can_maximize())
            return;
        if (w.get_maximized() === Meta.MaximizeFlags.BOTH)
            w.unmaximize(Meta.MaximizeFlags.BOTH);
        else
            w.maximize(Meta.MaximizeFlags.BOTH);
    }

    _minimize() {
        const w = this._focused;
        if (w && w.can_minimize())
            w.minimize();
    }

    _close_window() {
        const w = this._focused;
        if (w)
            w.delete(global.get_current_time());
    }

    _workspace(direction) {
        const current = global.workspace_manager.get_active_workspace();
        const next = current.get_neighbor(direction);
        if (next !== current)
            Main.wm.actionMoveWorkspace(next);
    }

    _workspace_left() {
        this._workspace(Meta.MotionDirection.LEFT);
    }

    _workspace_right() {
        this._workspace(Meta.MotionDirection.RIGHT);
    }

    _tabList() {
        const ws = global.workspace_manager.get_active_workspace();
        return global.display.get_tab_list(Meta.TabList.NORMAL, ws);
    }

    _switch_windows() {
        // como um toque rápido no Alt+Tab: a janela usada antes da atual
        const list = this._tabList();
        if (list.length > 1)
            Main.activateWindow(list[1]);
    }

    _switch_apps() {
        const list = this._tabList();
        const current = list.length ? this._tracker.get_window_app(list[0]) : null;
        const other = list.find(w => this._tracker.get_window_app(w) !== current);
        if (other)
            Main.activateWindow(other);
    }

    _show_desktop() {
        // mostra a área de trabalho; da próxima vez, devolve as mesmas janelas
        const visible = this._tabList().filter(w => !w.minimized && w.can_minimize());
        if (visible.length) {
            this._minimizedForDesktop = visible;
            visible.forEach(w => w.minimize());
        } else {
            const time = global.get_current_time();
            this._minimizedForDesktop.slice().reverse().forEach(w => {
                if (w.get_workspace())
                    w.unminimize();
            });
            const last = this._minimizedForDesktop[0];
            if (last && last.get_workspace())
                last.activate(time);
            this._minimizedForDesktop = [];
        }
    }
}

export default class MouseOptionsExtension extends Extension {
    enable() {
        this._actions = new ShellActions();
        this._dbus = Gio.DBusExportedObject.wrapJSObject(SHELL_IFACE, this._actions);
        this._dbus.export(Gio.DBus.session, SHELL_PATH);

        this._lastFocus = null;
        this._serviceUp = false;
        this._focusId = global.display.connect('notify::focus-window', () => this._pushFocus());
        this._watchId = Gio.bus_watch_name(Gio.BusType.SESSION, SERVICE, Gio.BusNameWatcherFlags.NONE,
            () => {
                this._serviceUp = true;
                this._lastFocus = null;
                this._pushFocus();   // o serviço acabou de (re)iniciar: conta quem está em foco
            },
            () => {
                this._serviceUp = false;
            });
    }

    disable() {
        global.display.disconnect(this._focusId);
        Gio.bus_unwatch_name(this._watchId);
        if (this._serviceUp)
            this._callService('ClearFocus', null);
        this._dbus.unexport();
        this._dbus = null;
        this._actions = null;
    }

    _focusNames() {
        const w = global.display.focus_window;
        if (!w)
            return [];
        const names = [w.get_wm_class(), w.get_wm_class_instance(), w.get_gtk_application_id(),
            w.get_sandboxed_app_id()];
        const app = Shell.WindowTracker.get_default().get_window_app(w);
        if (app && app.get_id() && !app.get_id().startsWith('window:'))   // "window:N" = app sem .desktop
            names.push(app.get_id().replace(/\.desktop$/, ''));
        const pid = w.get_pid();
        if (pid > 0)
            names.push(readComm(pid));
        return [...new Set(names.filter(n => n))];
    }

    _pushFocus() {
        if (!this._serviceUp)
            return;
        const names = this._focusNames();
        const key = names.join('\n');
        if (key === this._lastFocus)
            return;
        this._lastFocus = key;
        this._callService('SetFocus', new GLib.Variant('(as)', [names]));
    }

    _callService(method, params) {
        Gio.DBus.session.call(SERVICE, SERVICE_PATH, SERVICE_IFACE, method, params, null,
            Gio.DBusCallFlags.NO_AUTO_START, 1000, null, (conn, res) => {
                try {
                    conn.call_finish(res);
                } catch {
                    // serviço fora do ar: tudo bem, ele pede o foco quando voltar
                }
            });
    }
}
