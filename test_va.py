import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import va_core as c  # noqa: E402

fails = 0


def check(name, cond):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL ") + name)


# conversões
check("scalar 0.5 -> 50", c.scalar_to_percent(0.5) == 50)
check("scalar clamp", c.scalar_to_percent(2) == 100 and c.scalar_to_percent(-1) == 0)
check("percent 25 -> 0.25", c.percent_to_scalar(25) == 0.25)
check("percent clamp", c.percent_to_scalar(300) == 1.0 and c.percent_to_scalar("x") == 0.0)

# perfis com backend falso
fb = c.FakeBackend([("Spotify.exe", 80), ("chrome.exe", 40), ("Discord.exe", 100)], master=60)
prof = c.make_profile(fb.list_sessions(), 60)
check("perfil tem 3 apps", len(prof["apps"]) == 3 and prof["apps"]["spotify.exe"]["volume"] == 80)
fb.set_volume("fake0", 10)
fb.set_mute("fake1", True)
fb.set_master(5)
done, missing = c.apply_profile(prof, fb)
ss = {s.name: s for s in fb.list_sessions()}
check("aplica volume", ss["Spotify.exe"].volume == 80)
check("aplica mudo", ss["chrome.exe"].muted is False)
check("master intacto sem flag", fb.master == 5)
c.apply_profile(prof, fb, apply_master=True)
check("master com flag", fb.master == 60)
fb2 = c.FakeBackend([("SPOTIFY.EXE", 1)])
done, missing = c.apply_profile(prof, fb2)
check("casa sem diferenciar caixa", done == ["spotify.exe"] and fb2.list_sessions()[0].volume == 80)
check("ausentes listados", missing == ["chrome.exe", "discord.exe"])

# persistência
tmp = os.path.join(tempfile.mkdtemp(), "sub", "perfis.json")
c.save_profiles({"Jogo": prof}, tmp)
check("salva/carrega", c.load_profiles(tmp)["Jogo"]["apps"]["chrome.exe"]["volume"] == 40)
check("arquivo ausente -> {}", c.load_profiles(tmp + "x") == {})

# GUI offscreen com backend falso
from PyQt6.QtWidgets import QApplication  # noqa: E402
app = QApplication([])
sys.path.insert(0, HERE)
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("volume_apps_gui", os.path.join(HERE, "volume_apps.pyw"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
fb = c.FakeBackend([("a.exe", 30), ("b.exe", 70)], master=50)
w = m.VolumeApps(fb, profiles_path=tmp)
check("2 linhas", len(w.rows) == 2)
w.rows["fake0"].slider.setValue(55)
check("slider move backend", fb.list_sessions()[0].volume == 55)
w.rows["fake1"].mute.setChecked(True)
check("mudo move backend", fb.list_sessions()[1].muted)
w.master_row.slider.setValue(20)
check("master move backend", fb.master == 20)
fb._s["fake0"].volume = 90
w.refresh()
check("refresh reflete", w.rows["fake0"].slider.value() == 90)
w.combo.setCurrentText("Jogo")
w.apply_selected()
check("aplicar perfil via GUI (nada casa)", "Fora do ar" in w.status.text())
w.delete_selected()
check("apagar perfil", "Jogo" not in c.load_profiles(tmp))
fb._s.clear()
w.refresh()
check("linhas somem", len(w.rows) == 0)
w2 = m.VolumeApps(None, error="boom")
check("mensagem de erro amigável sem backend", w2.backend is None)

# teste real, somente leitura
try:
    rb = c.PycawBackend()
    ses = rb.list_sessions()
    rb.get_master()
    check(f"real: listou {len(ses)} sessão(ões) em '{rb.get_device_name()}'", True)
except Exception as ex:
    print("SKIP real:", ex)

print("FALHAS:", fails)
sys.exit(1 if fails else 0)
