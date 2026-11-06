"""Lógica do Volume por App: modelo de sessões, perfis e backends (real via pycaw / falso p/ testes)."""
import json
import os

PERFIS_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VolumeApps")
PERFIS_PATH = os.path.join(PERFIS_DIR, "perfis.json")


# ---------- conversões ----------
def scalar_to_percent(v):
    try:
        return int(round(max(0.0, min(1.0, float(v))) * 100))
    except (TypeError, ValueError):
        return 0


def percent_to_scalar(p):
    try:
        return max(0.0, min(100.0, float(p))) / 100.0
    except (TypeError, ValueError):
        return 0.0


def norm_name(name):
    """Normaliza nome de processo para casar perfis (minúsculas, sem espaços nas pontas)."""
    return (name or "").strip().lower()


class SessionInfo:
    """Foto de uma sessão de áudio (nome, volume 0-100, mudo, pico 0-100)."""

    def __init__(self, key, name, volume, muted=False, peak=0, pid=0, icon_path=""):
        self.key = key
        self.name = name
        self.volume = int(volume)
        self.muted = bool(muted)
        self.peak = int(peak)
        self.pid = pid
        self.icon_path = icon_path


# ---------- backend falso ----------
class FakeBackend:
    """Backend em memória: nenhum áudio real é tocado."""

    def __init__(self, sessions=None, master=50):
        self.master = master
        self.master_muted = False
        self.device_name = "Alto-falantes (Falso)"
        self._s = {}
        for i, (name, vol) in enumerate(sessions or []):
            self._s[f"fake{i}"] = SessionInfo(f"fake{i}", name, vol, pid=1000 + i)

    def list_sessions(self):
        return [SessionInfo(s.key, s.name, s.volume, s.muted, s.peak, s.pid) for s in self._s.values()]

    def set_volume(self, key, pct):
        if key in self._s:
            self._s[key].volume = max(0, min(100, int(pct)))

    def set_mute(self, key, m):
        if key in self._s:
            self._s[key].muted = bool(m)

    def get_master(self):
        return self.master, self.master_muted

    def set_master(self, pct):
        self.master = max(0, min(100, int(pct)))

    def set_master_mute(self, m):
        self.master_muted = bool(m)

    def get_device_name(self):
        return self.device_name


# ---------- backend real ----------
class PycawBackend:
    """Usa pycaw. Todas as chamadas devem vir da mesma thread (a da GUI)."""

    def __init__(self):
        import comtypes
        try:
            comtypes.CoInitialize()
        except OSError:
            pass
        from pycaw.pycaw import AudioUtilities
        self._au = AudioUtilities
        self._raw = {}
        self._dev()  # falha cedo se não houver áudio

    def _dev(self):
        return self._au.GetSpeakers()

    def list_sessions(self):
        out = []
        self._raw = {}
        for s in self._au.GetAllSessions():
            try:
                proc = s.Process
                if proc is not None:
                    name = proc.name()
                else:
                    name = "Sons do sistema" if s.ProcessId == 0 else (s.DisplayName or "Desconhecido")
                key = s.Identifier or s.InstanceIdentifier or f"pid{s.ProcessId}"
                vol = s.SimpleAudioVolume
                peak = 0
                try:
                    from pycaw.pycaw import IAudioMeterInformation
                    m = s._ctl.QueryInterface(IAudioMeterInformation)
                    peak = scalar_to_percent(m.GetPeakValue())
                except Exception:
                    pass
                self._raw[key] = s
                out.append(SessionInfo(key, name, scalar_to_percent(vol.GetMasterVolume()),
                                       bool(vol.GetMute()), peak, s.ProcessId or 0))
            except Exception:
                continue
        return out

    def set_volume(self, key, pct):
        s = self._raw.get(key)
        if s is not None:
            s.SimpleAudioVolume.SetMasterVolume(percent_to_scalar(pct), None)

    def set_mute(self, key, m):
        s = self._raw.get(key)
        if s is not None:
            s.SimpleAudioVolume.SetMute(1 if m else 0, None)

    def get_master(self):
        ev = self._dev().EndpointVolume
        return scalar_to_percent(ev.GetMasterVolumeLevelScalar()), bool(ev.GetMute())

    def set_master(self, pct):
        self._dev().EndpointVolume.SetMasterVolumeLevelScalar(percent_to_scalar(pct), None)

    def set_master_mute(self, m):
        self._dev().EndpointVolume.SetMute(1 if m else 0, None)

    def get_device_name(self):
        return self._dev().FriendlyName or "Dispositivo padrão"


# ---------- perfis ----------
def load_profiles(path=None):
    path = path or PERFIS_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_profiles(profiles, path=None):
    path = path or PERFIS_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def make_profile(sessions, master=None):
    """Perfil = {apps: {nome_processo: {volume, muted}}, master}. Nomes repetidos: vale o último."""
    apps = {}
    for s in sessions:
        apps[norm_name(s.name)] = {"volume": s.volume, "muted": s.muted}
    return {"apps": apps, "master": master}


def apply_profile(profile, backend, apply_master=False):
    """Aplica o perfil nas sessões ativas casando por nome. Retorna (aplicados, ausentes)."""
    apps = profile.get("apps", {})
    done = set()
    for s in backend.list_sessions():
        cfg = apps.get(norm_name(s.name))
        if cfg is None:
            continue
        backend.set_volume(s.key, cfg.get("volume", s.volume))
        backend.set_mute(s.key, cfg.get("muted", False))
        done.add(norm_name(s.name))
    if apply_master and profile.get("master") is not None:
        backend.set_master(profile["master"])
    missing = sorted(set(apps) - done)
    return sorted(done), missing
