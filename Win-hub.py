import os
import sys
import ctypes
import threading
import traceback
import subprocess
import shutil
import json
import webbrowser
import tempfile
import tkinter as tk
from tkinter import ttk
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageOps
except Exception:
    Image=None
    ImageDraw=None
    ImageOps=None

try:
    import winreg
except Exception:
    winreg=None

import customtkinter as ctk

APP_TITLE="Win Hub"
APPDATA_BASE=os.environ.get("APPDATA",os.getcwd())
APPDATA_ROOT=os.path.join(APPDATA_BASE,"Win Hub")
try:
    os.makedirs(APPDATA_ROOT,exist_ok=True)
except OSError:
    APPDATA_ROOT=os.path.join(tempfile.gettempdir(),"Win Hub")
    os.makedirs(APPDATA_ROOT,exist_ok=True)
LOG_DIR=APPDATA_ROOT
LOG_PATH=os.path.join(LOG_DIR,"control-hub.log")
SETTINGS_PATH=os.path.join(APPDATA_ROOT,"settings.json")

if getattr(sys,"frozen",False):
    base=getattr(sys,"_MEIPASS",os.path.dirname(sys.executable))
    os.environ.setdefault("TCL_LIBRARY",os.path.join(base,"tcl","tcl8.6"))
    os.environ.setdefault("TK_LIBRARY",os.path.join(base,"tcl","tk8.6"))

DEFAULT_THEME="Тёмно-синяя"
THEMES={
    "Тёмно-синяя":{"BG":"#0C1533","PANEL":"#0C1533","CARD":"#0F1E47","CARD_2":"#142A5F","TEXT":"#F8FAFF","MUTED":"#A9B9DE","BORDER":"#223265","ACCENT_1":"#1D4ED8","ACCENT_2":"#2563EB","ACCENT_3":"#93C5FD","OK":"#34D399","DANGER":"#FB7185","RGB":["#1D4ED8"]},
    "Графитовая":{"BG":"#050608","PANEL":"#050608","CARD":"#111827","CARD_2":"#1F2937","TEXT":"#F9FAFB","MUTED":"#9CA3AF","BORDER":"#374151","ACCENT_1":"#3B82F6","ACCENT_2":"#2563EB","ACCENT_3":"#D1D5DB","OK":"#34D399","DANGER":"#FB7185","RGB":["#3B82F6"]},
    "Фиолетовая":{"BG":"#120622","PANEL":"#120622","CARD":"#1F1036","CARD_2":"#321653","TEXT":"#FAF5FF","MUTED":"#C4B5FD","BORDER":"#4C1D95","ACCENT_1":"#A855F7","ACCENT_2":"#C084FC","ACCENT_3":"#DDD6FE","OK":"#34D399","DANGER":"#FB7185","RGB":["#A855F7"]},
    "Изумрудная":{"BG":"#02130F","PANEL":"#02130F","CARD":"#052E24","CARD_2":"#064E3B","TEXT":"#ECFDF5","MUTED":"#99F6E4","BORDER":"#047857","ACCENT_1":"#10B981","ACCENT_2":"#14B8A6","ACCENT_3":"#A7F3D0","OK":"#34D399","DANGER":"#FB7185","RGB":["#10B981"]},
    "Бордовая":{"BG":"#190308","PANEL":"#190308","CARD":"#3B0A16","CARD_2":"#5A1023","TEXT":"#FFF1F2","MUTED":"#FECDD3","BORDER":"#991B1B","ACCENT_1":"#EF4444","ACCENT_2":"#F87171","ACCENT_3":"#FECACA","OK":"#4ADE80","DANGER":"#FB7185","RGB":["#EF4444"]},
    "Серая":{"BG":"#060709","PANEL":"#060709","CARD":"#111827","CARD_2":"#1F2937","TEXT":"#F9FAFB","MUTED":"#9CA3AF","BORDER":"#4B5563","ACCENT_1":"#E5E7EB","ACCENT_2":"#F3F4F6","ACCENT_3":"#D1D5DB","OK":"#4ADE80","DANGER":"#FB7185","RGB":["#E5E7EB"]},
    "Тёмная бирюза":{"BG":"#031013","PANEL":"#031013","CARD":"#042529","CARD_2":"#06424A","TEXT":"#ECFEFF","MUTED":"#99F6E4","BORDER":"#0F766E","ACCENT_1":"#14B8A6","ACCENT_2":"#2DD4BF","ACCENT_3":"#99F6E4","OK":"#34D399","DANGER":"#FB7185","RGB":["#14B8A6"]}
}

_log_lock=threading.Lock()
_error_lock=threading.Lock()
ERROR_LOG_PATH=None

def log(msg:str):
    line=f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    with _log_lock:
        with open(LOG_PATH,"a",encoding="utf-8") as f:
            f.write(line+"\n")
    print(line,flush=True)

def _ensure_error_log_file():
    global ERROR_LOG_PATH
    if ERROR_LOG_PATH is None:
        ts=datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        ERROR_LOG_PATH=os.path.join(LOG_DIR,f"AppErrors.{ts}.txt")
    return ERROR_LOG_PATH

def log_error(msg:str):
    log("[ERROR] "+msg)
    try:
        path=_ensure_error_log_file()
        with _error_lock:
            with open(path,"a",encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def exception_hook(exctype,value,tb):
    text="".join(traceback.format_exception(exctype,value,tb))
    log_error(f"UNHANDLED EXCEPTION:\n{text}")

sys.excepthook=exception_hook

def is_windows():
    return os.name=="nt" and winreg is not None

def is_admin()->bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def elevate_if_needed():
    if not is_windows():
        return
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except Exception:
        return
    params=subprocess.list2cmdline(sys.argv[1:])
    exe=sys.executable
    try:
        rc=ctypes.windll.shell32.ShellExecuteW(None,"runas",exe,params,os.path.dirname(os.path.abspath(sys.argv[0])),1)
    except Exception as e:
        log_error(f"elevate_if_needed failed: {e}")
        return
    if isinstance(rc,int) and rc>32:
        sys.exit(0)

def load_ui_settings():
    data={"theme_name":DEFAULT_THEME}
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH,"r",encoding="utf-8") as f:
                raw=json.load(f)
            if isinstance(raw,dict):
                name=raw.get("theme_name") or raw.get("theme") or DEFAULT_THEME
                if name in ("Noir","Mahashe Graphite","Mahashe Noir"):
                    name=DEFAULT_THEME
                if raw.get("ui_revision") in (2,3) and isinstance(name,str) and name in THEMES:
                    data["theme_name"]=name
        except Exception as e:
            log_error(f"load_ui_settings error: {e}")
    return data

def save_ui_settings(theme_name):
    try:
        data={"theme_name":theme_name if theme_name in THEMES else DEFAULT_THEME,"ui_revision":3}
        with open(SETTINGS_PATH,"w",encoding="utf-8") as f:
            json.dump(data,f,ensure_ascii=False,indent=2)
    except Exception as e:
        log_error(f"save_ui_settings error: {e}")

def run_setx(name,value,system=False):
    if not is_windows():
        raise RuntimeError("Не Windows")
    cmd=["setx"]
    if system:
        cmd.append("/M")
    cmd += [name,str(value)]
    cp=subprocess.run(cmd,capture_output=True,text=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    return cp.returncode,cp.stdout,cp.stderr

def broadcast_env_change():
    if not is_windows():
        return
    try:
        HWND_BROADCAST=0xFFFF
        WM_SETTINGCHANGE=0x001A
        SMTO_ABORTIFHUNG=0x0002
        SendMessageTimeoutW=ctypes.windll.user32.SendMessageTimeoutW
        SendMessageTimeoutW(HWND_BROADCAST,WM_SETTINGCHANGE,0,ctypes.c_wchar_p("Environment"),SMTO_ABORTIFHUNG,2000,None)
    except Exception:
        pass

def sh_change_notify():
    if not is_windows():
        return
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000,0x0000,None,None)
    except Exception:
        pass

def ie4uinit_clear_icon_cache():
    if not is_windows():
        return
    try:
        ie4u=os.path.join(os.environ.get("SystemRoot",r"C:\Windows"),"System32","ie4uinit.exe")
        if os.path.isfile(ie4u):
            subprocess.run([ie4u,"-ClearIconCache"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    except Exception:
        pass

def _reg_access_read():
    return winreg.KEY_READ|getattr(winreg,"KEY_WOW64_64KEY",0)

def _reg_access_write():
    return winreg.KEY_SET_VALUE|winreg.KEY_CREATE_SUB_KEY|winreg.KEY_QUERY_VALUE|getattr(winreg,"KEY_WOW64_64KEY",0)

def reg_set_str(root,subkey,name,value,expand=False):
    k=winreg.CreateKeyEx(root,subkey,0,_reg_access_write())
    try:
        typ=winreg.REG_EXPAND_SZ if expand else winreg.REG_SZ
        winreg.SetValueEx(k,name,0,typ,str(value))
    finally:
        try:
            winreg.CloseKey(k)
        except Exception:
            pass

def reg_set_dword(root,subkey,name,value):
    k=winreg.CreateKeyEx(root,subkey,0,_reg_access_write())
    try:
        winreg.SetValueEx(k,name,0,winreg.REG_DWORD,int(value))
    finally:
        try:
            winreg.CloseKey(k)
        except Exception:
            pass

def reg_get_value(root,subkey,name,default=None):
    try:
        k=winreg.OpenKey(root,subkey,0,_reg_access_read())
    except FileNotFoundError:
        return default
    except Exception:
        return default
    try:
        v,_=winreg.QueryValueEx(k,name)
        return v
    except Exception:
        return default
    finally:
        try:
            winreg.CloseKey(k)
        except Exception:
            pass

def reg_delete_value(root,subkey,name):
    try:
        k=winreg.OpenKey(root,subkey,0,_reg_access_write())
    except FileNotFoundError:
        return False
    except Exception:
        return False
    try:
        winreg.DeleteValue(k,name)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False
    finally:
        try:
            winreg.CloseKey(k)
        except Exception:
            pass

def ensure_dir(path):
    try:
        os.makedirs(path,exist_ok=True)
        return True
    except Exception:
        return False

def move_dir_contents(src,dst):
    if not os.path.isdir(src):
        return
    ensure_dir(dst)
    try:
        for name in os.listdir(src):
            sp=os.path.join(src,name)
            dp=os.path.join(dst,name)
            if os.path.exists(dp):
                continue
            try:
                shutil.move(sp,dp)
            except Exception:
                try:
                    if os.path.isdir(sp):
                        shutil.copytree(sp,dp)
                        shutil.rmtree(sp,ignore_errors=True)
                    else:
                        shutil.copy2(sp,dp)
                        try:
                            os.remove(sp)
                        except Exception:
                            pass
                except Exception:
                    pass
    except Exception:
        pass

def normalize_icon_spec(p):
    p=(p or "").strip().strip('"')
    if not p:
        return ""
    if "," in p:
        return p
    return p+",0"

USER_SHELL_FOLDERS=r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
SHELL_FOLDERS=r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"

KNOWN_FOLDERS=[
    {"key":"desktop","name":"Рабочий стол","sub":"Desktop","keys":["Desktop"],"tpl":"Desktop"},
    {"key":"documents","name":"Документы","sub":"Documents","keys":["Personal"],"tpl":"Documents"},
    {"key":"pictures","name":"Изображения","sub":"Pictures","keys":["My Pictures"],"tpl":"Pictures"},
    {"key":"videos","name":"Видео","sub":"Videos","keys":["My Video"],"tpl":"Videos"},
    {"key":"downloads","name":"Загрузки","sub":"Downloads","keys":["Downloads","{374DE290-123F-4565-9164-39C4925E467B}"],"tpl":"Downloads"},
    {"key":"music","name":"Музыка","sub":"Music","keys":["My Music"],"tpl":"Music"},
    {"key":"favorites","name":"Избранное","sub":"Favorites","keys":["Favorites"],"tpl":"Favorites"},
    {"key":"searches","name":"Поиски","sub":"Searches","keys":["Searches"],"tpl":"Searches"},
    {"key":"savedgames","name":"Сохранённые игры","sub":"Saved Games","keys":["Saved Games"],"tpl":"Saved Games"},
    {"key":"links","name":"Ссылки","sub":"Links","keys":["Links"],"tpl":"Links"},
]

def get_current_shell_folder_path(keynames):
    for kn in keynames:
        v=reg_get_value(winreg.HKEY_CURRENT_USER,SHELL_FOLDERS,kn,None)
        if isinstance(v,str) and v.strip():
            return v
    for kn in keynames:
        v=reg_get_value(winreg.HKEY_CURRENT_USER,USER_SHELL_FOLDERS,kn,None)
        if isinstance(v,str) and v.strip():
            return os.path.expandvars(v)
    return None

def set_shell_folder_path(keynames,new_path):
    new_path=str(new_path)
    for kn in keynames:
        reg_set_str(winreg.HKEY_CURRENT_USER,USER_SHELL_FOLDERS,kn,new_path,expand=True)
    for kn in keynames:
        reg_set_str(winreg.HKEY_CURRENT_USER,SHELL_FOLDERS,kn,os.path.expandvars(new_path),expand=False)

def apply_known_folders(changes,move_existing=True):
    for item,newp in changes.items():
        if not newp:
            continue
        oldp=get_current_shell_folder_path(item["keys"])
        ensure_dir(newp)
        set_shell_folder_path(item["keys"],newp)
        if move_existing and oldp and os.path.isdir(oldp) and os.path.abspath(oldp).lower()!=os.path.abspath(newp).lower():
            move_dir_contents(oldp,newp)
    sh_change_notify()

def apply_temp_paths(user_temp,user_tmp,sys_temp,sys_tmp):
    if user_temp:
        ensure_dir(user_temp)
        reg_set_str(winreg.HKEY_CURRENT_USER,r"Environment","TEMP",user_temp,expand=False)
        reg_set_str(winreg.HKEY_CURRENT_USER,r"Environment","TMP",user_tmp or user_temp,expand=False)
        try:
            os.environ["TEMP"]=user_temp
            os.environ["TMP"]=user_tmp or user_temp
        except Exception:
            pass
        run_setx("TEMP",user_temp,system=False)
        run_setx("TMP",user_tmp or user_temp,system=False)
    if sys_temp or sys_tmp:
        if not is_admin():
            raise PermissionError("Нужны права администратора для System TEMP/TMP")
        st=sys_temp or sys_tmp
        sp=sys_tmp or sys_temp
        if st:
            ensure_dir(st)
        if sp:
            ensure_dir(sp)
        base=r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
        if st:
            reg_set_str(winreg.HKEY_LOCAL_MACHINE,base,"TEMP",st,expand=False)
        if sp:
            reg_set_str(winreg.HKEY_LOCAL_MACHINE,base,"TMP",sp,expand=False)
        if st:
            run_setx("TEMP",st,system=True)
        if sp:
            run_setx("TMP",sp,system=True)
    broadcast_env_change()

ICON_DRIVE_C=r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\DriveIcons\C\DefaultIcon"
ICON_DRIVE_GENERIC=r"SOFTWARE\Classes\Drive\DefaultIcon"
ICON_REMOVABLE=r"SOFTWARE\Classes\RemovableDrive\DefaultIcon"
ICON_FOLDER=r"SOFTWARE\Classes\Folder\DefaultIcon"
CLSID_DESKTOP=r"SOFTWARE\Classes\CLSID\{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}\DefaultIcon"
CLSID_DOCUMENTS=r"SOFTWARE\Classes\CLSID\{FDD39AD0-238F-46AF-ADB4-6C85480369C7}\DefaultIcon"
CLSID_PICTURES=r"SOFTWARE\Classes\CLSID\{33E28130-4E1E-4676-835A-98395C3BC3BB}\DefaultIcon"
CLSID_VIDEOS=r"SOFTWARE\Classes\CLSID\{18989B1D-99B5-455B-841C-AB7C74E4DDFC}\DefaultIcon"

def apply_icons(specs):
    if not is_admin():
        raise PermissionError("Нужны права администратора для смены системных иконок")
    for subkey,val in specs.items():
        if not val:
            continue
        reg_set_str(winreg.HKEY_LOCAL_MACHINE,subkey,"",normalize_icon_spec(val),expand=False)
    sh_change_notify()
    ie4uinit_clear_icon_cache()

IFEO_BASE=r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"
CPU_CHOICES=[("Низкий",1),("Ниже среднего",5),("Обычный",8),("Выше среднего",6),("Высокий",3)]
CPU_NAME_BY_VAL={v:n for n,v in CPU_CHOICES}
CPU_VAL_BY_NAME={n:v for n,v in CPU_CHOICES}

GPU_PREF_KEY=r"Software\Microsoft\DirectX\UserGpuPreferences"
GPU_PREF_HIGHPERF="GpuPreference=2;"

HKLM_GAMES_PATH=r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
GAMES_SETTINGS={"GPU Priority":8,"Priority":6,"Scheduling Category":"High","SFIO Priority":"High"}

def normalize_exe_name(s):
    s=(s or "").strip().strip('"').strip()
    if not s:
        return ""
    s=s.replace("/","\\")
    base=os.path.basename(s)
    if base.lower().endswith(".exe"):
        return base
    if "\\" in s or ":" in s:
        if base:
            return base if base.lower().endswith(".exe") else base+".exe"
    return s if s.lower().endswith(".exe") else s+".exe"

def enum_ifeo_cpu_priority():
    res=[]
    try:
        k0=winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,IFEO_BASE,0,_reg_access_read())
    except FileNotFoundError:
        return []
    except Exception as e:
        raise RuntimeError(str(e))
    i=0
    while True:
        try:
            sub=winreg.EnumKey(k0,i)
            i+=1
        except OSError:
            break
        psub=IFEO_BASE+"\\"+sub+r"\PerfOptions"
        v=reg_get_value(winreg.HKEY_LOCAL_MACHINE,psub,"CpuPriorityClass",None)
        if v is None:
            continue
        try:
            vi=int(v)
        except Exception:
            continue
        res.append({"exe":sub,"value":vi})
    try:
        winreg.CloseKey(k0)
    except Exception:
        pass
    res.sort(key=lambda x:(x.get("exe") or "").lower())
    return res

def set_ifeo_cpu_priority(exe,value):
    exe=normalize_exe_name(exe)
    if not exe:
        raise ValueError("Пустое имя exe")
    if not is_admin():
        raise PermissionError("Нужны права администратора (HKLM)")
    sub=IFEO_BASE+"\\"+exe+r"\PerfOptions"
    reg_set_dword(winreg.HKEY_LOCAL_MACHINE,sub,"CpuPriorityClass",int(value))

def delete_ifeo_cpu_priority(exe):
    exe=normalize_exe_name(exe)
    if not exe:
        raise ValueError("Пустое имя exe")
    if not is_admin():
        raise PermissionError("Нужны права администратора (HKLM)")
    sub=IFEO_BASE+"\\"+exe+r"\PerfOptions"
    ok=reg_delete_value(winreg.HKEY_LOCAL_MACHINE,sub,"CpuPriorityClass")
    return ok

def apply_games_profile():
    if not is_admin():
        raise PermissionError("Нужны права администратора для Games профиля")
    for k,v in GAMES_SETTINGS.items():
        if isinstance(v,int):
            reg_set_dword(winreg.HKEY_LOCAL_MACHINE,HKLM_GAMES_PATH,k,v)
        else:
            reg_set_str(winreg.HKEY_LOCAL_MACHINE,HKLM_GAMES_PATH,k,v,expand=False)

def set_gpu_high_perf(full_path):
    if not full_path:
        return False
    p=str(full_path).strip().strip('"')
    if not p:
        return False
    reg_set_str(winreg.HKEY_CURRENT_USER,GPU_PREF_KEY,p,GPU_PREF_HIGHPERF,expand=False)
    return True

def delete_gpu_pref(full_path):
    p=str(full_path or "").strip().strip('"')
    if not p:
        return False
    return reg_delete_value(winreg.HKEY_CURRENT_USER,GPU_PREF_KEY,p)

class ToastManager:
    def __init__(self,root):
        self.root=root
        self.active=[]
    def show(self,title,text,ms=3000,width=360,bg="#0f1e47",border="#223265"):
        win=ctk.CTkToplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost",True)
        win.attributes("-alpha",0.0)
        win.configure(fg_color=bg)
        frame=ctk.CTkFrame(win,fg_color=bg,corner_radius=12,border_width=1,border_color=border)
        frame.pack(fill="both",expand=True)
        title_lbl=ctk.CTkLabel(frame,text=title,font=ctk.CTkFont(size=13,weight="bold"))
        body_lbl=ctk.CTkLabel(frame,text=text,font=ctk.CTkFont(size=12),justify="left")
        title_lbl.pack(anchor="w",padx=14,pady=(10,2))
        body_lbl.pack(anchor="w",padx=14,pady=(0,12))
        win.update_idletasks()
        h=frame.winfo_reqheight()+2
        x=self.root.winfo_screenwidth()-width-16
        y=self.root.winfo_screenheight()-16-(len(self.active)*(h+10))-h
        win.geometry(f"{width}x{h}+{x}+{y}")
        self.active.append(win)
        self._fade(win,0.0,0.98,step=0.08,delay=20)
        win.after(ms,lambda:self._dismiss(win))
    def _fade(self,win,a_from,a_to,step=0.05,delay=25):
        a=a_from+step
        if (step>0 and a>=a_to) or (step<0 and a<=a_to):
            try:
                win.attributes("-alpha",a_to)
            except Exception:
                pass
            return
        try:
            win.attributes("-alpha",a)
        except Exception:
            return
        win.after(delay,lambda:self._fade(win,a,a_to,step,delay))
    def _dismiss(self,win):
        if not win.winfo_exists():
            return
        try:
            cur=float(win.attributes("-alpha"))
        except Exception:
            cur=0.9
        self._fade(win,cur,0.0,step=-0.08,delay=20)
        win.after(220,lambda:self._destroy(win))
    def _destroy(self,win):
        if win in self.active:
            self.active.remove(win)
        try:
            win.destroy()
        except Exception:
            pass

_executor=threading.Semaphore(1)

def _require_windows_registry():
    if winreg is None or os.name!="nt":
        raise RuntimeError("Требуется Windows")

def _env_root_path(scope):
    if scope=="user":
        return winreg.HKEY_CURRENT_USER,r"Environment"
    if scope=="machine":
        return winreg.HKEY_LOCAL_MACHINE,r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
    raise ValueError("scope должен быть user или machine")

def _open_env_key(scope,access):
    _require_windows_registry()
    root,path=_env_root_path(scope)
    return winreg.CreateKeyEx(root,path,0,access)

def list_env(scope):
    _require_windows_registry()
    out={}
    with _open_env_key(scope,winreg.KEY_READ) as k:
        i=0
        while True:
            try:
                name,val,vtype=winreg.EnumValue(k,i)
            except OSError:
                break
            out[str(name)]=(str(val),int(vtype))
            i+=1
    return out

def get_env(scope,name):
    _require_windows_registry()
    try:
        with _open_env_key(scope,winreg.KEY_READ) as k:
            val,vtype=winreg.QueryValueEx(k,name)
            return str(val),int(vtype)
    except Exception:
        return None

def set_env(scope,name,value):
    _require_windows_registry()
    if scope=="machine" and not is_admin():
        raise PermissionError("Требуются права администратора для MACHINE")
    vtype=winreg.REG_EXPAND_SZ if "%" in (value or "") else winreg.REG_SZ
    with _open_env_key(scope,winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k,name,0,vtype,value)
    broadcast_env_change()

def delete_env(scope,name):
    _require_windows_registry()
    if scope=="machine" and not is_admin():
        raise PermissionError("Требуются права администратора для MACHINE")
    try:
        with _open_env_key(scope,winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k,name)
    except FileNotFoundError:
        pass
    broadcast_env_change()

def _split_path(raw):
    out=[]
    for p in (raw or "").split(os.pathsep):
        p=p.strip()
        if p:
            out.append(p)
    return out

def _join_path(parts):
    return os.pathsep.join(parts)

def read_path(scope):
    cur=get_env(scope,"Path")
    if not cur:
        return []
    return _split_path(cur[0])

def write_path(scope,parts):
    set_env(scope,"Path",_join_path(parts))

def expand_exists(p):
    try:
        return os.path.exists(os.path.expandvars(p))
    except Exception:
        return False

def dedup_keep_first(parts):
    seen=set()
    out=[]
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

def prune_nonexistent(parts):
    return [p for p in parts if expand_exists(p)]

def add_path_once(parts,new_p):
    if new_p and new_p not in parts:
        parts.append(new_p)
    return parts

def rm_path_exact(parts,target):
    return [p for p in parts if p!=target]

class BigEditDialog(ctk.CTkToplevel):
    def __init__(self,parent,theme,title,name="",value="",name_editable=True):
        super().__init__(parent)
        self.theme=theme
        self.result=None
        self.title(title)
        self.geometry("780x430")
        self.resizable(False,False)
        self.configure(fg_color=theme["BG"])
        self.grab_set()
        self.transient(parent)
        card=ctk.CTkFrame(self,fg_color=theme["CARD"],corner_radius=18,border_width=1,border_color=theme["BORDER"])
        card.pack(fill="both",expand=True,padx=14,pady=14)
        card.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(card,text=title,font=ctk.CTkFont(family="Segoe UI",size=16,weight="bold"),text_color=theme["TEXT"]).grid(row=0,column=0,columnspan=2,sticky="w",padx=14,pady=(12,8))
        ctk.CTkLabel(card,text="Имя:",font=ctk.CTkFont(family="Segoe UI",size=12,weight="bold"),text_color=theme["TEXT"]).grid(row=1,column=0,sticky="w",padx=14,pady=(0,6))
        self.ent_name=ctk.CTkEntry(card,height=34,fg_color=theme["CARD_2"],text_color=theme["TEXT"],border_color=theme["BORDER"])
        self.ent_name.grid(row=2,column=0,columnspan=2,sticky="ew",padx=14,pady=(0,12))
        self.ent_name.insert(0,name or "")
        if not name_editable:
            self.ent_name.configure(state="disabled")
        ctk.CTkLabel(card,text="Значение:",font=ctk.CTkFont(family="Segoe UI",size=12,weight="bold"),text_color=theme["TEXT"]).grid(row=3,column=0,sticky="w",padx=14,pady=(0,6))
        self.txt_val=ctk.CTkTextbox(card,height=220,corner_radius=12,border_width=1,border_color=theme["BORDER"],fg_color=theme["CARD_2"],text_color=theme["TEXT"],wrap="word")
        self.txt_val.grid(row=4,column=0,columnspan=2,sticky="nsew",padx=14,pady=(0,10))
        self.txt_val.insert("1.0",value or "")
        btns=ctk.CTkFrame(card,fg_color=theme["CARD"],corner_radius=0)
        btns.grid(row=5,column=0,columnspan=2,sticky="ew",padx=14,pady=(0,14))
        btns.grid_columnconfigure(0,weight=1)
        ctk.CTkButton(btns,text="Сохранить",corner_radius=13,width=120,height=32,command=self._ok).pack(side="left")
        ctk.CTkButton(btns,text="Отмена",corner_radius=13,width=100,height=32,command=self._cancel).pack(side="right")
        self._center()

    def _center(self):
        self.update_idletasks()
        sw=self.winfo_screenwidth()
        sh=self.winfo_screenheight()
        w=self.winfo_width()
        h=self.winfo_height()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _ok(self):
        name=(self.ent_name.get() or "").strip()
        val=self.txt_val.get("1.0","end").rstrip("\n")
        if not name:
            return
        self.result=(name,val)
        self.destroy()

    def _cancel(self):
        self.result=None
        self.destroy()


class ValueDialog(ctk.CTkToplevel):
    def __init__(self,parent,theme,title,prompt,value="",multiline=False,accept_text="Готово"):
        super().__init__(parent)
        self.theme=theme
        self.result=None
        self.multiline=multiline
        self.title(title)
        self.geometry("560x330" if multiline else "560x220")
        self.configure(fg_color=theme["BG"])
        self.resizable(False,False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW",self._cancel)
        card=ctk.CTkFrame(self,fg_color=theme["CARD"],corner_radius=18,border_width=1,border_color=theme["BORDER"])
        card.pack(fill="both",expand=True,padx=14,pady=14)
        card.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(card,text=title,font=ctk.CTkFont(family="Segoe UI",size=18,weight="bold"),text_color=theme["TEXT"]).grid(row=0,column=0,sticky="w",padx=18,pady=(16,4))
        ctk.CTkLabel(card,text=prompt,font=ctk.CTkFont(family="Segoe UI",size=12),text_color=theme["MUTED"],justify="left",wraplength=500).grid(row=1,column=0,sticky="w",padx=18,pady=(0,12))
        if multiline:
            self.field=ctk.CTkTextbox(card,height=130,corner_radius=10,border_width=1,border_color=theme["BORDER"],fg_color=theme["CARD_2"],text_color=theme["TEXT"],wrap="word")
            self.field.insert("1.0",value)
        else:
            self.field=ctk.CTkEntry(card,height=38,corner_radius=10,border_width=1,border_color=theme["BORDER"],fg_color=theme["CARD_2"],text_color=theme["TEXT"])
            self.field.insert(0,value)
        self.field.grid(row=2,column=0,sticky="ew",padx=18,pady=(0,14))
        actions=ctk.CTkFrame(card,fg_color="transparent",corner_radius=0)
        actions.grid(row=3,column=0,sticky="ew",padx=18,pady=(0,16))
        actions.grid_columnconfigure(0,weight=1)
        ctk.CTkButton(actions,text="Отмена",width=104,height=34,corner_radius=10,fg_color=theme["CARD_2"],hover_color=theme["BORDER"],text_color=theme["TEXT"],command=self._cancel).grid(row=0,column=0,sticky="w")
        ctk.CTkButton(actions,text=accept_text,width=122,height=34,corner_radius=10,fg_color=theme["ACCENT_1"],hover_color=theme["ACCENT_2"],text_color=theme["BG"],command=self._ok).grid(row=0,column=1,sticky="e")
        self.after(100,self._focus)
        self.update_idletasks()
        w=self.winfo_width()
        h=self.winfo_height()
        self.geometry(f"{w}x{h}+{(self.winfo_screenwidth()-w)//2}+{(self.winfo_screenheight()-h)//2}")

    def _focus(self):
        self.field.focus_set()
        if not self.multiline:
            self.field.select_range(0,"end")

    def _ok(self):
        self.result=self.field.get("1.0","end").rstrip("\n") if self.multiline else self.field.get()
        self.destroy()

    def _cancel(self):
        self.result=None
        self.destroy()


class ActionDialog(ctk.CTkToplevel):
    def __init__(self,parent,theme,title,description,actions):
        super().__init__(parent)
        self.parent=parent
        self.title(title)
        self.configure(fg_color=theme["BG"])
        self.resizable(False,False)
        self.transient(parent)
        self.grab_set()
        height=min(560,178+len(actions)*48)
        self.geometry(f"460x{height}")
        self.protocol("WM_DELETE_WINDOW",self.destroy)
        card=ctk.CTkFrame(self,fg_color=theme["CARD"],corner_radius=16,border_width=0)
        card.pack(fill="both",expand=True,padx=12,pady=12)
        card.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(card,text=title,font=ctk.CTkFont(family="Segoe UI",size=18,weight="bold"),text_color=theme["TEXT"]).grid(row=0,column=0,sticky="w",padx=18,pady=(16,2))
        ctk.CTkLabel(card,text=description,font=ctk.CTkFont(family="Segoe UI",size=12),text_color=theme["MUTED"],justify="left",wraplength=400).grid(row=1,column=0,sticky="w",padx=18,pady=(0,14))
        for index,(label,callback,accent) in enumerate(actions,start=2):
            fg=theme["ACCENT_1"] if accent else theme["CARD_2"]
            hover=theme["ACCENT_2"] if accent else theme["BORDER"]
            text=theme["BG"] if accent else theme["TEXT"]
            ctk.CTkButton(card,text=label,height=36,corner_radius=10,anchor="w",fg_color=fg,hover_color=hover,text_color=text,border_width=0,font=ctk.CTkFont(family="Segoe UI",size=12,weight="bold"),command=lambda cb=callback:self._choose(cb)).grid(row=index,column=0,sticky="ew",padx=18,pady=(0,8))
        ctk.CTkButton(card,text="Закрыть",height=32,corner_radius=10,fg_color="transparent",hover_color=theme["CARD_2"],text_color=theme["MUTED"],border_width=0,font=ctk.CTkFont(family="Segoe UI",size=12,weight="bold"),command=self.destroy).grid(row=2+len(actions),column=0,sticky="e",padx=18,pady=(4,14))
        self._center()

    def _center(self):
        self.update_idletasks()
        w=self.winfo_width()
        h=self.winfo_height()
        self.geometry(f"{w}x{h}+{(self.winfo_screenwidth()-w)//2}+{(self.winfo_screenheight()-h)//2}")

    def _choose(self,callback):
        self.destroy()
        self.parent.after(0,callback)


class ConfirmDialog(ctk.CTkToplevel):
    def __init__(self,parent,theme,title,text,confirm_text):
        super().__init__(parent)
        self.result=False
        self.title(title)
        self.geometry("460x230")
        self.configure(fg_color=theme["BG"])
        self.resizable(False,False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW",self._cancel)
        card=ctk.CTkFrame(self,fg_color=theme["CARD"],corner_radius=16,border_width=0)
        card.pack(fill="both",expand=True,padx=12,pady=12)
        card.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(card,text=title,font=ctk.CTkFont(family="Segoe UI",size=18,weight="bold"),text_color=theme["TEXT"]).grid(row=0,column=0,sticky="w",padx=18,pady=(16,6))
        ctk.CTkLabel(card,text=text,font=ctk.CTkFont(family="Segoe UI",size=12),text_color=theme["MUTED"],justify="left",wraplength=400).grid(row=1,column=0,sticky="w",padx=18,pady=(0,18))
        actions=ctk.CTkFrame(card,fg_color="transparent",corner_radius=0)
        actions.grid(row=2,column=0,sticky="ew",padx=18,pady=(0,16))
        actions.grid_columnconfigure(0,weight=1)
        ctk.CTkButton(actions,text="Отмена",width=110,height=34,corner_radius=10,fg_color=theme["CARD_2"],hover_color=theme["BORDER"],text_color=theme["TEXT"],border_width=0,font=ctk.CTkFont(family="Segoe UI",size=12,weight="bold"),command=self._cancel).grid(row=0,column=0,sticky="w")
        ctk.CTkButton(actions,text=confirm_text,width=150,height=34,corner_radius=10,fg_color=theme["ACCENT_1"],hover_color=theme["ACCENT_2"],text_color=theme["BG"],border_width=0,font=ctk.CTkFont(family="Segoe UI",size=12,weight="bold"),command=self._confirm).grid(row=0,column=1,sticky="e")
        self.update_idletasks()
        w=self.winfo_width()
        h=self.winfo_height()
        self.geometry(f"{w}x{h}+{(self.winfo_screenwidth()-w)//2}+{(self.winfo_screenheight()-h)//2}")

    def _confirm(self):
        self.result=True
        self.destroy()

    def _cancel(self):
        self.result=False
        self.destroy()



class App(ctk.CTk):
    def __init__(self,ui_settings):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.theme_name=ui_settings.get("theme_name",DEFAULT_THEME)
        if self.theme_name not in THEMES:
            self.theme_name=DEFAULT_THEME
        self._set_palette()
        self.title(APP_TITLE)
        self.geometry("980x680")
        self.minsize(900,620)
        self.configure(fg_color=self.BG)
        self.settings_win=None
        self.toaster=ToastManager(self)
        self.avatar_ctk_image=None
        self.sf_by_tab={}
        self.pages={}
        self.nav_buttons={}
        self.tabs=None
        self.rgb_cards=[]
        self.rgb_phase=0.0
        self.current_page="Главная"
        self.status_var=ctk.StringVar(value="Готово")
        self.page_order=["Главная","Папки","TEMP","Path","Переменные среды","Иконки","Оптимизация"]
        self.page_subtitles={
            "Главная":"Главный экран Win Hub и быстрый доступ к возможностям приложения.",
            "Папки":"Перенос системных пользовательских каталогов и заполнение путей по шаблону.",
            "TEMP":"Настройка TEMP/TMP пользователя и системы с обновлением окружения.",
            "Path":"Редактор PATH пользователя и системы: добавление, удаление, очистка дубликатов.",
            "Переменные среды":"Просмотр, создание, редактирование и удаление переменных окружения.",
            "Иконки":"Системные иконки дисков, папок и специальных разделов Windows.",
            "Оптимизация":"IFEO-приоритеты процессов, GPU High Performance и Games профиль."
        }
        self._build_shell()
        self.tab_home=self.pages["Главная"]
        self.tab_folders=self.pages["Папки"]
        self.tab_temp=self.pages["TEMP"]
        self.tab_path=self.pages["Path"]
        self.tab_env=self.pages["Переменные среды"]
        self.tab_icons=self.pages["Иконки"]
        self.tab_opt=self.pages["Оптимизация"]
        self.tab_about=self.pages["Главная"]
        self._build_tab_home()
        self._build_tab_folders()
        self._build_tab_temp()
        self._build_tab_path()
        self._build_tab_env()
        self._build_tab_icons()
        self._build_tab_opt()
        self._apply_theme_recursive(self)
        self.show_page("Главная")
        self.bind_all("<MouseWheel>",self._on_wheel,add="+")
        self.bind_all("<Button-4>",lambda e:self._scroll(-120),add="+")
        self.bind_all("<Button-5>",lambda e:self._scroll(120),add="+")
        self.bind_all("<Control-v>",self._ctrl_paste,add="+")
        self.bind_all("<Control-V>",self._ctrl_paste,add="+")
        self.bind_all("<Control-c>",self._ctrl_copy,add="+")
        self.bind_all("<Control-C>",self._ctrl_copy,add="+")
        self.bind_all("<Control-a>",self._ctrl_select_all,add="+")
        self.bind_all("<Control-A>",self._ctrl_select_all,add="+")
        self.after(200,self.refresh_all)

    def _set_palette(self):
        td=THEMES.get(self.theme_name,THEMES[DEFAULT_THEME])
        self.BG=td["BG"]
        self.PANEL=td["PANEL"]
        self.CARD=td["CARD"]
        self.CARD_2=td["CARD_2"]
        self.TEXT=td["TEXT"]
        self.MUTED=td["MUTED"]
        self.BORDER=td["BORDER"]
        self.ACCENT_1=td["ACCENT_1"]
        self.ACCENT_2=td["ACCENT_2"]
        self.ACCENT_3=td["ACCENT_3"]
        self.OK=td["OK"]
        self.DANGER=td["DANGER"]
        self.RGB=list(td.get("RGB",[self.ACCENT_1,self.ACCENT_2,self.ACCENT_3,self.OK,self.DANGER]))
        self.BLUE=self.ACCENT_1

    def _mix(self,a,b,t):
        try:
            a=a.lstrip("#")
            b=b.lstrip("#")
            ar,ag,ab=int(a[0:2],16),int(a[2:4],16),int(a[4:6],16)
            br,bg,bb=int(b[0:2],16),int(b[2:4],16),int(b[4:6],16)
            return f"#{int(ar+(br-ar)*t):02x}{int(ag+(bg-ag)*t):02x}{int(ab+(bb-ab)*t):02x}"
        except Exception:
            return a

    def _font(self,size=13,weight=None,slant=None):
        kwargs={"family":"Segoe UI Variable","size":size}
        if weight is not None:
            kwargs["weight"]=weight
        if slant is not None:
            kwargs["slant"]=slant
        return ctk.CTkFont(**kwargs)

    def _build_shell(self):
        self.grid_rowconfigure(0,weight=1)
        self.grid_columnconfigure(0,weight=1)
        self.shell=ctk.CTkFrame(self,fg_color=self.BG,corner_radius=0)
        self.shell._is_root_bg=True
        self.shell.grid(row=0,column=0,sticky="nsew",padx=12,pady=12)
        self.shell.grid_rowconfigure(1,weight=1)
        self.shell.grid_columnconfigure(0,weight=1)
        self._build_header()
        self.content_area=ctk.CTkFrame(self.shell,fg_color=self.BG,corner_radius=0)
        self.content_area._is_root_bg=True
        self.content_area.grid(row=1,column=0,sticky="nsew",pady=(0,0))
        self.content_area.grid_rowconfigure(0,weight=1)
        self.content_area.grid_columnconfigure(0,weight=1)
        self.tabs=ctk.CTkTabview(self.content_area,corner_radius=15,border_width=1,border_color=self.BORDER,fg_color=self.BG,segmented_button_fg_color=self.CARD,segmented_button_selected_color=self.ACCENT_1,segmented_button_selected_hover_color=self.ACCENT_2,segmented_button_unselected_color=self.CARD,segmented_button_unselected_hover_color=self.CARD_2,text_color=self.TEXT)
        self.tabs.grid(row=0,column=0,sticky="nsew")
        for name in self.page_order:
            page=self.tabs.add(name)
            page.configure(fg_color=self.BG)
            page._is_page=True
            page._page_name=name
            page._page_subtitle=self.page_subtitles.get(name,"")
            self.pages[name]=page
        self.tabs.set(self.current_page)

    def _find_account_picture(self):
        candidates=[]
        appdata=os.environ.get("APPDATA")
        programdata=os.environ.get("ProgramData",r"C:\ProgramData")
        userprofile=os.environ.get("USERPROFILE")
        if appdata:
            folder=Path(appdata)/"Microsoft"/"Windows"/"AccountPictures"
            if folder.exists():
                try:
                    candidates.extend(sorted(folder.glob("*.png"),key=lambda p:p.stat().st_mtime,reverse=True))
                except Exception:
                    pass
        if userprofile:
            candidates.append(Path(userprofile)/"AppData"/"Roaming"/"Microsoft"/"Windows"/"AccountPictures"/"user.png")
        candidates.extend([Path(programdata)/"Microsoft"/"User Account Pictures"/"user.png",Path(programdata)/"Microsoft"/"User Account Pictures"/"guest.png"])
        for path in candidates:
            try:
                if path.exists() and path.suffix.lower()==".png":
                    return path
            except Exception:
                pass
        return None

    def _make_avatar_image(self,size=48):
        path=self._find_account_picture()
        if not path or Image is None or ImageDraw is None or ImageOps is None:
            return None
        try:
            source=Image.open(path).convert("RGBA")
            resampling=getattr(getattr(Image,"Resampling",Image),"LANCZOS")
            avatar=ImageOps.fit(source,(size,size),method=resampling,centering=(0.5,0.5))
            mask=Image.new("L",(size,size),0)
            draw=ImageDraw.Draw(mask)
            draw.ellipse((0,0,size-1,size-1),fill=255)
            avatar.putalpha(mask)
            return ctk.CTkImage(light_image=avatar,dark_image=avatar,size=(size,size))
        except Exception:
            return None

    def _profile_label(self,parent,text,size=12,weight=None,color_role=None):
        color=self.TEXT
        if color_role=="muted":
            color=self.MUTED
        if color_role=="accent":
            color=self.ACCENT_1
        lbl=ctk.CTkLabel(parent,text=text,font=self._font(size,weight),text_color=color)
        if color_role:
            lbl._color_role=color_role
        return lbl

    def _build_header(self):
        self.header=ctk.CTkFrame(self.shell,fg_color=self.BG,corner_radius=0)
        self.header._is_root_bg=True
        self.header.grid(row=0,column=0,sticky="ew",pady=(0,12))
        self.header.grid_columnconfigure(1,weight=1)
        ctk.CTkLabel(self.header,text="Win Hub",font=self._font(22,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w")
        self.refresh_button=ctk.CTkButton(self.header,text="Действия",width=110,height=34,corner_radius=15,font=self._font(12,"bold"),command=self.open_actions_window)
        self.refresh_button._is_accent_button=True
        self.refresh_button.grid(row=0,column=2,sticky="e",padx=(10,8))
        self.settings_button=ctk.CTkButton(self.header,text="⚙",width=40,height=34,corner_radius=15,font=self._font(15,"bold"),command=self.open_settings_window)
        self.settings_button._is_secondary_accent_button=True
        self.settings_button.grid(row=0,column=3,sticky="e")

    def _style_nav_buttons(self):
        return

    def show_page(self,name):
        if name not in self.pages:
            return
        self.current_page=name
        if self.tabs is not None:
            self.tabs.set(name)

    def _clear_toasts(self):
        try:
            for w in list(self.toaster.active):
                try:
                    w.destroy()
                except Exception:
                    pass
            self.toaster.active.clear()
            if hasattr(self,"status_var"):
                self.status_var.set("Тосты очищены")
        except Exception:
            pass

    def _show_actions(self,title,description,actions):
        dialog=ActionDialog(self,self._theme_dict(),title,description,actions)
        self.wait_window(dialog)

    def _confirm(self,title,text,confirm_text="Продолжить"):
        dialog=ConfirmDialog(self,self._theme_dict(),title,text,confirm_text)
        self.wait_window(dialog)
        return bool(dialog.result)

    def open_actions_window(self):
        self._show_actions("Действия","Общие команды приложения.",[("Обновить данные",self.refresh_all,True),("Открыть папку логов",self.open_log_dir,False),("Очистить уведомления",self._clear_toasts,False)])

    def open_path_actions(self):
        self._show_actions("Действия PATH","Команды применяются к выбранной строке или текущему списку.",[("Редактировать выбранный путь",self.path_edit_selected,True),("Удалить выбранные пути",self.path_delete_selected,False),("Удалить дубликаты",self.path_dedup,False),("Удалить несуществующие",self.path_prune,False),("Обновить список",self.path_reload,False)])

    def open_env_actions(self):
        self._show_actions("Переменные среды","Управление выбранной переменной.",[("Создать переменную",self.env_create,True),("Редактировать выбранную",self.env_edit_selected,False),("Удалить выбранную",self.env_delete_selected,False),("Обновить список",self.env_reload,False)])

    def open_icons_actions(self):
        self._show_actions("Иконки","Изменения системных иконок применяются после подтверждения.",[("Применить изменения",self.apply_icons_ui,True),("Обновить кэш иконок",self.refresh_icons,False)])

    def open_opt_actions(self):
        self._show_actions("Оптимизация","Команды работают с указанным исполняемым файлом.",[("Добавить или обновить",self.apply_opt,True),("Удалить настройку",self.delete_opt,False),("Обновить список",self.refresh_opt_list,False)])

    def open_about_dialog(self):
        self.show_page("Главная")

    def _card(self,parent,corner_radius=14,height=None):
        frame=ctk.CTkFrame(parent,fg_color=self.CARD,corner_radius=15,border_width=1,border_color=self.BORDER)
        frame._is_card=True
        frame._is_rgb_card=True
        if height:
            frame.configure(height=height)
        return frame

    def _animate_rgb_cards(self):
        self.rgb_phase=(self.rgb_phase+0.008)%len(self.RGB)
        cards=[]
        for index,shell in enumerate(self.rgb_cards):
            try:
                if shell.winfo_exists():
                    position=(self.rgb_phase+index*0.42)%len(self.RGB)
                    base=int(position)
                    next_index=(base+1)%len(self.RGB)
                    color=self._mix(self.RGB[base],self.RGB[next_index],position-base)
                    shell.configure(border_color=color)
                    cards.append(shell)
            except Exception:
                pass
        self.rgb_cards=cards
        try:
            self.after(40,self._animate_rgb_cards)
        except Exception:
            pass

    def _scrollable(self,parent):
        sf=ctk.CTkScrollableFrame(
            parent,
            corner_radius=22,
            fg_color=self.BG,
            border_width=0,
            scrollbar_button_color=self.CARD_2,
            scrollbar_button_hover_color=self.ACCENT_1,
            scrollbar_fg_color=self.BG,
        )
        sf._is_scrollable=True
        sf.pack(fill="both",expand=True,padx=4,pady=(0,0))
        return sf

    def _active_sf(self):
        return self.sf_by_tab.get(self.current_page)

    def _scroll(self,delta):
        sf=self._active_sf()
        if not sf:
            return
        try:
            sf._parent_canvas.yview_scroll(int(-delta/15),"units")
        except Exception:
            pass

    def _on_wheel(self,e):
        sf=self._active_sf()
        if not sf:
            return None
        self._scroll(e.delta)
        return "break"

    def toast_ok(self,title,text):
        if hasattr(self,"status_var"):
            self.status_var.set(f"{title}: {text}")
        self.toaster.show(title,text,ms=3200,width=440,bg=self.CARD,border=self._mix(self.OK,self.CARD,0.35))

    def toast_fail(self,title,text):
        if hasattr(self,"status_var"):
            self.status_var.set(f"{title}: {text}")
        self.toaster.show(title,text,ms=4600,width=540,bg=self.CARD,border=self._mix(self.DANGER,self.CARD,0.32))

    def _apply_theme_recursive(self,widget):
        try:
            if isinstance(widget,ctk.CTkScrollableFrame):
                widget.configure(fg_color=self.BG,border_width=0,scrollbar_button_color=self.CARD_2,scrollbar_button_hover_color=self.ACCENT_1,scrollbar_fg_color=self.BG)
            elif isinstance(widget,ctk.CTkFrame):
                if getattr(widget,"_is_sidebar",False):
                    widget.configure(fg_color=self.PANEL)
                    if widget is getattr(self,"sidebar",None):
                        widget.configure(border_color=self._mix(self.BORDER,self.PANEL,0.35))
                elif getattr(widget,"_is_profile_card",False):
                    widget.configure(fg_color=self._mix(self.CARD,self.PANEL,0.25),border_color=self._mix(self.ACCENT_1,self.PANEL,0.62))
                elif getattr(widget,"_is_profile_inner",False):
                    widget.configure(fg_color="transparent")
                elif getattr(widget,"_is_avatar_shell",False):
                    widget.configure(fg_color=self._mix(self.CARD_2,self.PANEL,0.16),border_color=self._mix(self.ACCENT_1,self.PANEL,0.12))
                elif getattr(widget,"_is_sidebar_footer",False):
                    widget.configure(fg_color=self._mix(self.CARD,self.PANEL,0.35),border_color=self._mix(self.BORDER,self.PANEL,0.35))
                elif getattr(widget,"_is_card",False):
                    widget.configure(fg_color=self.CARD,border_width=1)
                elif getattr(widget,"_is_page",False) or getattr(widget,"_is_root_bg",False):
                    widget.configure(fg_color=self.BG)
                elif hasattr(widget,"master") and getattr(widget.master,"_is_card",False):
                    widget.configure(fg_color=self.CARD)
                elif hasattr(widget,"master") and getattr(widget.master,"_is_sidebar",False):
                    widget.configure(fg_color=self.PANEL)
                else:
                    widget.configure(fg_color=self.BG)
            elif isinstance(widget,ctk.CTkTextbox):
                widget.configure(fg_color=self.CARD_2,text_color=self.TEXT,border_width=1,border_color=self._mix(self.BORDER,self.ACCENT_1,0.18))
            elif isinstance(widget,ctk.CTkEntry):
                widget.configure(fg_color=self.CARD_2,text_color=self.TEXT,placeholder_text_color=self.MUTED,border_width=1,border_color=self._mix(self.BORDER,self.ACCENT_1,0.15))
            elif isinstance(widget,ctk.CTkLabel):
                if getattr(widget,"_is_chip",False):
                    status_color=self.OK if is_admin() else self.DANGER
                    widget.configure(text_color=status_color)
                elif getattr(widget,"_color_role",None)=="muted":
                    widget.configure(text_color=self.MUTED)
                elif getattr(widget,"_color_role",None)=="accent":
                    widget.configure(text_color=self.ACCENT_1)
                else:
                    widget.configure(text_color=getattr(widget,"_text_color_override",None) or widget.cget("text_color"))
            elif isinstance(widget,ctk.CTkButton):
                if getattr(widget,"_is_nav_button",False):
                    pass
                elif getattr(widget,"_is_gear_button",False):
                    widget.configure(width=30,height=26,corner_radius=13,fg_color=self._mix(self.CARD_2,self.ACCENT_2,0.18),hover_color=self._mix(self.CARD_2,self.ACCENT_2,0.32),text_color=self.TEXT,border_width=1,border_color=self._mix(self.ACCENT_2,self.CARD_2,0.35))
                elif getattr(widget,"_is_accent_button",False):
                    widget.configure(fg_color=self._mix(self.CARD_2,self.ACCENT_1,0.22),hover_color=self._mix(self.CARD_2,self.ACCENT_1,0.36),text_color=self.TEXT,border_width=1,border_color=self._mix(self.ACCENT_1,self.CARD_2,0.35))
                elif getattr(widget,"_is_secondary_accent_button",False):
                    widget.configure(fg_color=self._mix(self.CARD_2,self.ACCENT_2,0.18),hover_color=self._mix(self.CARD_2,self.ACCENT_2,0.32),text_color=self.TEXT,border_width=1,border_color=self._mix(self.ACCENT_2,self.CARD_2,0.35))
                else:
                    widget.configure(height=34,corner_radius=11,font=self._font(12,"bold"),fg_color=self.CARD_2,hover_color=self._mix(self.CARD_2,self.ACCENT_1,0.22),text_color=self.TEXT,border_width=1,border_color=self._mix(self.BORDER,self.ACCENT_1,0.18))
            elif isinstance(widget,ctk.CTkCheckBox):
                widget.configure(text_color=self.TEXT,fg_color=self.ACCENT_1,hover_color=self._mix(self.ACCENT_1,self.CARD_2,0.35),border_color=self.BORDER,checkmark_color=self.BG)
            elif isinstance(widget,ctk.CTkOptionMenu):
                widget.configure(fg_color=self.CARD_2,button_color=self._mix(self.CARD_2,self.ACCENT_1,0.22),button_hover_color=self._mix(self.CARD_2,self.ACCENT_1,0.35),text_color=self.TEXT,dropdown_fg_color=self.CARD,dropdown_hover_color=self.CARD_2,dropdown_text_color=self.TEXT)
        except Exception:
            pass
        if hasattr(widget,"winfo_children"):
            for ch in widget.winfo_children():
                self._apply_theme_recursive(ch)
        try:
            if getattr(widget,"_is_accent_line",False):
                widget.configure(fg_color=self.ACCENT_2)
        except Exception:
            pass
        if widget is self:
            try:
                self._style_nav_buttons()
            except Exception:
                pass

    def on_theme_changed(self,value):
        if value not in THEMES:
            return
        self.theme_name=value
        self._set_palette()
        self.configure(fg_color=self.BG)
        save_ui_settings(self.theme_name)
        try:
            self.sidebar_theme_label.configure(text=f"Тема: {self.theme_name}")
        except Exception:
            pass
        self._configure_tree_style()
        self._apply_theme_recursive(self)
        if self.settings_win is not None and self.settings_win.winfo_exists():
            try:
                self.settings_win.configure(fg_color=self.BG)
                self._apply_theme_recursive(self.settings_win)
            except Exception:
                pass
        if hasattr(self,"status_var"):
            self.status_var.set(f"Тема изменена: {self.theme_name}")

    def open_settings_window(self):
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.lift()
            self.settings_win.focus_force()
            return
        win=ctk.CTkToplevel(self)
        win.title("Настройки")
        win.geometry("480x300")
        win.configure(fg_color=self.BG)
        win.grab_set()
        win.resizable(False,False)
        self.settings_win=win
        root=ctk.CTkFrame(win,fg_color=self.BG,corner_radius=0)
        root._is_root_bg=True
        root.pack(fill="both",expand=True,padx=14,pady=14)
        card=self._card(root)
        card.pack(fill="both",expand=True,padx=4,pady=4)
        card.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(card,text="Настройки",font=self._font(20,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=18,pady=(18,4))
        ctk.CTkLabel(card,text="Тема интерфейса",font=self._font(12,"bold"),text_color=self.MUTED).grid(row=1,column=0,sticky="w",padx=18,pady=(8,6))
        var=ctk.StringVar(value=self.theme_name)
        menu=ctk.CTkOptionMenu(card,values=list(THEMES.keys()),variable=var,command=self.on_theme_changed,width=260,height=36,corner_radius=10,font=self._font(12,"bold"))
        menu.grid(row=2,column=0,sticky="w",padx=18,pady=(0,16))
        rights="Режим администратора" if is_admin() else "Часть системных действий требует администратора"
        rights_color=self.OK if is_admin() else self.ACCENT_3
        ctk.CTkLabel(card,text=rights,font=self._font(11,"bold"),text_color=rights_color).grid(row=3,column=0,sticky="w",padx=18,pady=(0,16))
        ctk.CTkButton(card,text="Готово",width=96,height=32,corner_radius=10,command=win.destroy).grid(row=4,column=0,sticky="e",padx=18,pady=(0,18))
        self._apply_theme_recursive(win)

    def open_log_dir(self):
        try:
            if is_windows():
                os.startfile(LOG_DIR)
            else:
                subprocess.Popen(["xdg-open",LOG_DIR])
            if hasattr(self,"status_var"):
                self.status_var.set(f"Открыта папка логов: {LOG_DIR}")
        except Exception:
            self.toast_fail("Ошибка","Не удалось открыть папку логов")

    def refresh_opt_list(self):
        if not hasattr(self,"opt_list_container"):
            return
        def worker():
            return enum_ifeo_cpu_priority() if is_windows() else []
        def done(items):
            self._refresh_opt_list_body(items)
            try:
                self._apply_theme_recursive(self.opt_list_container)
            except Exception:
                pass
        def fail(text):
            log_error(f"enum_ifeo_cpu_priority error: {text}")
            self._refresh_opt_list_body([])
        self._run_worker("Оптимизация",worker,done,fail)

    def refresh_all(self):
        try:
            if hasattr(self,"path_tree"):
                self.path_reload()
        except Exception:
            pass
        try:
            if hasattr(self,"env_tree"):
                self.env_reload(silent=True)
        except Exception:
            pass
        try:
            self.refresh_opt_list()
            if hasattr(self,"status_var"):
                self.status_var.set("Данные интерфейса обновлены")
        except Exception:
            pass

    def _ctrl_paste(self,e):
        w=self.focus_get()
        if not w:
            return
        try:
            w.event_generate("<<Paste>>")
            return "break"
        except Exception:
            pass
        try:
            txt=self.clipboard_get()
        except Exception:
            return
        try:
            w.insert("insert",txt)
            return "break"
        except Exception:
            return


    def _ctrl_copy(self,e):
        w=self.focus_get()
        if not w:
            return
        try:
            w.event_generate("<<Copy>>")
            return "break"
        except Exception:
            pass
        try:
            sel=None
            try:
                sel=w.selection_get()
            except Exception:
                try:
                    sel=w.get("sel.first","sel.last")
                except Exception:
                    sel=None
            if sel:
                self.clipboard_clear()
                self.clipboard_append(sel)
                return "break"
        except Exception:
            return


    def _ctrl_select_all(self,e):
        w=self.focus_get()
        if not w:
            return
        try:
            if hasattr(w,"select_range"):
                w.select_range(0,"end")
                try:
                    w.icursor("end")
                except Exception:
                    pass
                return "break"
        except Exception:
            pass
        try:
            w.tag_add("sel","1.0","end")
            return "break"
        except Exception:
            return


    def _build_tab_folders(self):
        sf=self._scrollable(self.tab_folders)
        self.sf_by_tab["Папки"]=sf
        self.folders_template_var=ctk.StringVar(value="")
        self.folders_move_var=ctk.BooleanVar(value=True)
        self.folder_vars={it["key"]:ctk.StringVar(value="") for it in KNOWN_FOLDERS}
        self.folder_summary_labels={}
        hero=self._card(sf)
        hero.pack(fill="x",padx=8,pady=8)
        hero.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(hero,text="Папки Windows",font=self._font(20,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=18,pady=(18,2))
        ctk.CTkLabel(hero,text="Нажми «Указать» — путь выбирается в отдельном окне. На странице остаются только выбранные значения.",font=self._font(12),text_color=self.MUTED,wraplength=760,justify="left").grid(row=1,column=0,sticky="w",padx=18,pady=(0,14))
        ctk.CTkButton(hero,text="Шаблон путей",width=126,height=34,corner_radius=10,command=self.edit_folders_template).grid(row=0,column=1,rowspan=2,sticky="e",padx=18,pady=18)
        card_main=self._card(sf)
        card_main.pack(fill="x",padx=8,pady=(0,8))
        ctk.CTkLabel(card_main,text="Основные папки",font=self._font(14,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=14,pady=(14,10))
        for row,key in enumerate(("desktop","documents","pictures","videos"),start=1):
            item=next(x for x in KNOWN_FOLDERS if x["key"]==key)
            self.folder_summary_labels[key]=self._choice_button(card_main,row,item["name"],"Не указано",lambda k=key:self.pick_folder_for_key(k))
        card_other=self._card(sf)
        card_other.pack(fill="x",padx=8,pady=(0,8))
        ctk.CTkLabel(card_other,text="Другие расположения",font=self._font(14,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=14,pady=(14,10))
        for row,key in enumerate(("downloads","favorites","searches","music","links","savedgames"),start=1):
            item=next(x for x in KNOWN_FOLDERS if x["key"]==key)
            self.folder_summary_labels[key]=self._choice_button(card_other,row,item["name"],"Не указано",lambda k=key:self.pick_folder_for_key(k))
        footer=self._card(sf)
        footer.pack(fill="x",padx=8,pady=(0,8))
        footer.grid_columnconfigure(0,weight=1)
        ctk.CTkCheckBox(footer,text="Переместить существующие файлы",variable=self.folders_move_var,font=self._font(12,"bold")).grid(row=0,column=0,sticky="w",padx=16,pady=14)
        ctk.CTkButton(footer,text="Заполнить текущими",width=142,height=34,corner_radius=10,command=self.fill_current_folders).grid(row=0,column=1,sticky="e",padx=(0,8),pady=14)
        ctk.CTkButton(footer,text="Применить",width=108,height=34,corner_radius=10,command=self.apply_folders).grid(row=0,column=2,sticky="e",padx=(0,16),pady=14)

    def edit_folders_template(self):
        value=self._ask_value("Шаблон папок","Укажи базовую папку. Программа подставит в неё стандартные подпапки Windows.",self.folders_template_var.get(),False,"Заполнить")
        if value is None:
            return
        self.folders_template_var.set(value.strip().strip('"'))
        self.apply_folders_template()


    def apply_folders_template(self):
        base=(self.folders_template_var.get() or "").strip().strip('"')
        if not base:
            self.toast_fail("Ошибка","Пустой шаблон")
            return
        excluded={"desktop","documents","pictures","videos"}
        for it in KNOWN_FOLDERS:
            if it["key"] in excluded:
                continue
            p=os.path.join(base,it["tpl"])
            self.folder_vars[it["key"]].set(p)
            self._set_folder_summary(it["key"])
        self.toast_ok("Шаблон","Заполнены другие расположения. Основные папки не изменены")


    def pick_folder_for_key(self,key):
        from tkinter import filedialog
        d=filedialog.askdirectory(parent=self,title="Выберите папку")
        if not d:
            return
        self.folder_vars[key].set(d)
        self._set_folder_summary(key)


    def fill_current_folders(self):
        for it in KNOWN_FOLDERS:
            cur=get_current_shell_folder_path(it["keys"])
            if cur:
                self.folder_vars[it["key"]].set(cur)
                self._set_folder_summary(it["key"])
        self.toast_ok("Готово","Текущие пути подставлены")


    def apply_folders(self):
        if not is_windows():
            self.toast_fail("Ошибка","Это работает только на Windows")
            return
        changes={}
        for it in KNOWN_FOLDERS:
            newp=(self.folder_vars[it["key"]].get() or "").strip().strip('"')
            if newp:
                changes[it]=newp
        if not changes:
            self.toast_fail("Ошибка","Не задано ни одного пути")
            return
        move_existing=bool(self.folders_move_var.get())
        if not self._confirm("Изменить папки",f"Будет обновлено путей: {len(changes)}. Изменения затронут пользовательские каталоги Windows.","Применить"):
            return
        def worker():
            apply_known_folders(changes,move_existing=move_existing)
            return "Применено"
        def done(text):
            self.toast_ok("Папки",text)
        def fail(text):
            self.toast_fail("Ошибка",text or "Не удалось применить пути папок")
        self._run_worker("Папки",worker,done,fail,exclusive=True)

    def _build_tab_temp(self):
        sf=self._scrollable(self.tab_temp)
        self.sf_by_tab["TEMP"]=sf
        self.user_temp_var=ctk.StringVar(value="")
        self.user_tmp_var=ctk.StringVar(value="")
        self.sys_temp_var=ctk.StringVar(value="")
        self.sys_tmp_var=ctk.StringVar(value="")
        self.temp_template_var=ctk.StringVar(value="")
        self.temp_summary_labels={}
        hero=self._card(sf)
        hero.pack(fill="x",padx=8,pady=8)
        hero.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(hero,text="Временные файлы",font=self._font(20,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=18,pady=(18,2))
        ctk.CTkLabel(hero,text="Пути TEMP и TMP выбираются через отдельный диалог, без постоянных полей ввода.",font=self._font(12),text_color=self.MUTED).grid(row=1,column=0,sticky="w",padx=18,pady=(0,14))
        ctk.CTkButton(hero,text="Шаблон путей",width=126,height=34,corner_radius=10,command=self.edit_temp_template).grid(row=0,column=1,rowspan=2,sticky="e",padx=18,pady=18)
        card_user=self._card(sf)
        card_user.pack(fill="x",padx=8,pady=(0,8))
        ctk.CTkLabel(card_user,text="Пользователь",font=self._font(14,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=14,pady=(14,10))
        self.temp_summary_labels["user_temp"]=self._choice_button(card_user,1,"TEMP","Не указано",lambda:self.pick_temp_dir(self.user_temp_var,"user_temp"))
        self.temp_summary_labels["user_tmp"]=self._choice_button(card_user,2,"TMP","Не указано",lambda:self.pick_temp_dir(self.user_tmp_var,"user_tmp"))
        card_system=self._card(sf)
        card_system.pack(fill="x",padx=8,pady=(0,8))
        ctk.CTkLabel(card_system,text="Система",font=self._font(14,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=14,pady=(14,10))
        self.temp_summary_labels["sys_temp"]=self._choice_button(card_system,1,"TEMP","Не указано",lambda:self.pick_temp_dir(self.sys_temp_var,"sys_temp"))
        self.temp_summary_labels["sys_tmp"]=self._choice_button(card_system,2,"TMP","Не указано",lambda:self.pick_temp_dir(self.sys_tmp_var,"sys_tmp"))
        footer=self._card(sf)
        footer.pack(fill="x",padx=8,pady=(0,8))
        footer.grid_columnconfigure(0,weight=1)
        ctk.CTkButton(footer,text="Заполнить текущими",width=142,height=34,corner_radius=10,command=self.fill_current_temp).grid(row=0,column=1,sticky="e",padx=(0,8),pady=14)
        ctk.CTkButton(footer,text="Применить",width=108,height=34,corner_radius=10,command=self.apply_temp).grid(row=0,column=2,sticky="e",padx=(0,16),pady=14)

    def edit_temp_template(self):
        value=self._ask_value("Шаблон TEMP/TMP","Укажи базовую папку. Программа создаст варианты для пользователя и системы.",self.temp_template_var.get(),False,"Заполнить")
        if value is None:
            return
        self.temp_template_var.set(value.strip().strip('"'))
        self.apply_temp_template()


    def pick_temp_dir(self,target_var,key):
        from tkinter import filedialog
        d=filedialog.askdirectory(parent=self,title="Выберите папку")
        if not d:
            return
        target_var.set(d)
        self._set_temp_summary(key,target_var)


    def apply_temp_template(self):
        base=(self.temp_template_var.get() or "").strip().strip('"')
        if not base:
            self.toast_fail("Ошибка","Пустой шаблон")
            return
        self.user_temp_var.set(os.path.join(base,"TempUser"))
        self.user_tmp_var.set(os.path.join(base,"TmpUser"))
        self.sys_temp_var.set(os.path.join(base,"TempSystem"))
        self.sys_tmp_var.set(os.path.join(base,"TmpSystem"))
        self._set_temp_summary("user_temp",self.user_temp_var)
        self._set_temp_summary("user_tmp",self.user_tmp_var)
        self._set_temp_summary("sys_temp",self.sys_temp_var)
        self._set_temp_summary("sys_tmp",self.sys_tmp_var)
        self.toast_ok("Шаблон","Пути подставлены")


    def fill_current_temp(self):
        ut=reg_get_value(winreg.HKEY_CURRENT_USER,r"Environment","TEMP","")
        um=reg_get_value(winreg.HKEY_CURRENT_USER,r"Environment","TMP","")
        self.user_temp_var.set(str(ut or ""))
        self.user_tmp_var.set(str(um or ""))
        st=reg_get_value(winreg.HKEY_LOCAL_MACHINE,r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment","TEMP","")
        sm=reg_get_value(winreg.HKEY_LOCAL_MACHINE,r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment","TMP","")
        self.sys_temp_var.set(str(st or ""))
        self.sys_tmp_var.set(str(sm or ""))
        self._set_temp_summary("user_temp",self.user_temp_var)
        self._set_temp_summary("user_tmp",self.user_tmp_var)
        self._set_temp_summary("sys_temp",self.sys_temp_var)
        self._set_temp_summary("sys_tmp",self.sys_tmp_var)
        self.toast_ok("Готово","Текущие значения подставлены")


    def apply_temp(self):
        if not is_windows():
            self.toast_fail("Ошибка","Это работает только на Windows")
            return
        ut=(self.user_temp_var.get() or "").strip().strip('"')
        um=(self.user_tmp_var.get() or "").strip().strip('"')
        st=(self.sys_temp_var.get() or "").strip().strip('"')
        sm=(self.sys_tmp_var.get() or "").strip().strip('"')
        if not self._confirm("Изменить TEMP/TMP","Будут обновлены переменные окружения пользователя и системы.","Применить"):
            return
        def worker():
            apply_temp_paths(ut,um,st,sm)
            return "Применено"
        def done(text):
            self.toast_ok("TEMP/TMP",text)
        def fail(text):
            self.toast_fail("TEMP/TMP",text or "Не удалось применить TEMP/TMP")
        self._run_worker("TEMP/TMP",worker,done,fail,exclusive=True)

    def _run_worker(self,title,worker,on_success=None,on_error=None,exclusive=False):
        if exclusive and not _executor.acquire(False):
            self.toast_fail("Занято","Дождись завершения текущей операции")
            return
        if hasattr(self,"status_var"):
            self.status_var.set(f"{title}: выполняется...")
        def runner():
            acquired=exclusive
            try:
                result=worker()
                def done():
                    try:
                        if not self.winfo_exists():
                            return
                    except Exception:
                        return
                    if on_success:
                        on_success(result)
                    elif hasattr(self,"status_var"):
                        self.status_var.set(f"{title}: готово")
                self.after(0,done)
            except Exception as e:
                text=str(e)
                log_error(f"{title} error: {traceback.format_exc()}")
                def fail():
                    try:
                        if not self.winfo_exists():
                            return
                    except Exception:
                        return
                    if on_error:
                        on_error(text)
                    else:
                        self.toast_fail(title,text)
                self.after(0,fail)
            finally:
                if acquired:
                    try:
                        _executor.release()
                    except Exception:
                        pass
        threading.Thread(target=runner,daemon=True).start()

    def _configure_tree_style(self):
        try:
            style=ttk.Style(self)
            try:
                style.theme_use("clam")
            except Exception:
                pass
            style.configure("Mahashe.Treeview",background=self.CARD_2,fieldbackground=self.CARD_2,foreground=self.TEXT,bordercolor=self.BORDER,lightcolor=self.BORDER,darkcolor=self.BORDER,rowheight=34,font=("Segoe UI",10))
            style.configure("Mahashe.Treeview.Heading",background=self.CARD,foreground=self.TEXT,relief="flat",font=("Segoe UI",10,"bold"))
            style.map("Mahashe.Treeview",background=[("selected",self._mix(self.CARD_2,self.ACCENT_1,0.35))],foreground=[("selected",self.TEXT)])
        except Exception:
            pass

    def _selected_path_values(self):
        if not hasattr(self,"path_tree"):
            return []
        out=[]
        for iid in self.path_tree.selection():
            p=self._path_iid_to_path.get(iid)
            if p is not None:
                out.append(p)
        return out

    def _selected_env_item(self):
        if not hasattr(self,"env_tree"):
            return None
        sel=self.env_tree.selection()
        if not sel:
            return None
        return self._env_iid_to_item.get(sel[0])

    def _theme_dict(self):
        return {"BG":self.BG,"PANEL":self.PANEL,"CARD":self.CARD,"CARD_2":self.CARD_2,"TEXT":self.TEXT,"MUTED":self.MUTED,"BORDER":self.BORDER,"BLUE":self.ACCENT_1,"ACCENT_1":self.ACCENT_1,"ACCENT_2":self.ACCENT_2,"ACCENT_3":self.ACCENT_3,"OK":self.OK,"WARN":self.ACCENT_3,"BAD":self.DANGER,"DANGER":self.DANGER}

    def _compact_value(self,value,empty="Не указано"):
        text=(value or "").strip()
        if not text:
            return empty
        return text if len(text)<=70 else "…"+text[-67:]

    def _ask_value(self,title,prompt,value="",multiline=False,accept_text="Готово"):
        dlg=ValueDialog(self,self._theme_dict(),title,prompt,value,multiline,accept_text)
        self.wait_window(dlg)
        return dlg.result

    def _set_folder_summary(self,key):
        label=getattr(self,"folder_summary_labels",{}).get(key)
        if label:
            label.configure(text=self._compact_value(self.folder_vars[key].get()))

    def _set_temp_summary(self,key,var):
        label=getattr(self,"temp_summary_labels",{}).get(key)
        if label:
            label.configure(text=self._compact_value(var.get()))

    def _set_icon_summary(self,key):
        label=getattr(self,"icon_summary_labels",{}).get(key)
        if label:
            label.configure(text=self._compact_value(self.icon_vars[key].get(),"Иконка не выбрана"))

    def _choice_button(self,parent,row,label,summary,command,button_text="Указать"):
        parent.grid_columnconfigure(0,weight=1)
        tile=ctk.CTkFrame(parent,fg_color=self.CARD_2,corner_radius=12,border_width=0)
        tile.grid(row=row,column=0,sticky="ew",padx=14,pady=(0,8))
        tile.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(tile,text=label,font=self._font(12,"bold"),text_color=self.TEXT,anchor="w").grid(row=0,column=0,sticky="ew",padx=(14,8),pady=(10,0))
        value=ctk.CTkLabel(tile,text=summary,font=self._font(11),text_color=self.MUTED,anchor="w")
        value.grid(row=1,column=0,sticky="ew",padx=(14,8),pady=(0,10))
        ctk.CTkButton(tile,text=button_text,width=92,height=32,corner_radius=9,fg_color=self.CARD,hover_color=self.BORDER,text_color=self.TEXT,font=self._font(11,"bold"),command=command).grid(row=0,column=1,rowspan=2,sticky="e",padx=(8,10),pady=10)
        return value

    def _build_tab_path(self):
        root=ctk.CTkFrame(self.tab_path,fg_color=self.BG,corner_radius=0)
        root._is_root_bg=True
        root.pack(fill="both",expand=True,padx=4,pady=0)
        root.grid_rowconfigure(1,weight=1)
        root.grid_columnconfigure(0,weight=1)
        self.sf_by_tab["Path"]=None
        self.path_scope=ctk.StringVar(value="both")
        self.path_search_var=ctk.StringVar(value="")
        self._path_items=[]
        self._path_iid_to_path={}
        self._path_filter_after=None
        self._configure_tree_style()

        top=self._card(root)
        top.grid(row=0,column=0,sticky="ew",padx=8,pady=8)
        top.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(top,text="PATH",font=self._font(20,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=18,pady=(16,0))
        self.path_scope_label=ctk.CTkLabel(top,text="Область: USER + MACHINE",font=self._font(11,"bold"),text_color=self.ACCENT_3)
        self.path_scope_label.grid(row=1,column=0,sticky="w",padx=18,pady=(2,16))
        self.path_filter_label=ctk.CTkLabel(top,text="Фильтр не задан",font=self._font(11),text_color=self.MUTED)
        self.path_filter_label.grid(row=1,column=1,sticky="e",padx=(8,12),pady=(2,16))
        ctk.CTkButton(top,text="Область",width=88,height=32,corner_radius=10,command=self.choose_path_scope).grid(row=0,column=1,sticky="e",padx=(8,8),pady=16)
        ctk.CTkButton(top,text="Поиск",width=78,height=32,corner_radius=10,fg_color=self.CARD_2,hover_color=self.BORDER,command=self.edit_path_filter).grid(row=0,column=2,sticky="e",padx=(0,18),pady=16)

        self.path_list=self._card(root)
        self.path_list.grid(row=1,column=0,sticky="nsew",padx=8,pady=8)
        self.path_list.grid_rowconfigure(1,weight=1)
        self.path_list.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(self.path_list,text="Элементы PATH",font=self._font(14,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=14,pady=(12,6))
        wrap=tk.Frame(self.path_list,bg=self.CARD)
        wrap.grid(row=1,column=0,sticky="nsew",padx=14,pady=(0,14))
        wrap.grid_rowconfigure(0,weight=1)
        wrap.grid_columnconfigure(0,weight=1)
        self.path_tree=ttk.Treeview(wrap,columns=("status","path"),show="headings",selectmode="extended",style="Mahashe.Treeview")
        self.path_tree.heading("status",text="Статус")
        self.path_tree.heading("path",text="Путь")
        self.path_tree.column("status",width=90,minwidth=70,anchor="center",stretch=False)
        self.path_tree.column("path",width=760,minwidth=260,anchor="w",stretch=True)
        ybar=ttk.Scrollbar(wrap,orient="vertical",command=self.path_tree.yview)
        xbar=ttk.Scrollbar(wrap,orient="horizontal",command=self.path_tree.xview)
        self.path_tree.configure(yscrollcommand=ybar.set,xscrollcommand=xbar.set)
        self.path_tree.grid(row=0,column=0,sticky="nsew")
        ybar.grid(row=0,column=1,sticky="ns")
        xbar.grid(row=1,column=0,sticky="ew")
        self.path_tree.tag_configure("valid",foreground=self.OK)
        self.path_tree.tag_configure("invalid",foreground=self.DANGER)
        self.path_tree.tag_configure("duplicate",foreground=self.ACCENT_3)
        self.path_tree.bind("<Double-Button-1>",lambda _e:self.path_edit_selected())
        self.path_tree.bind("<Button-3>",self.path_context_menu)

        bottom=ctk.CTkFrame(root,fg_color=self.BG,corner_radius=0)
        bottom.grid(row=2,column=0,sticky="ew",padx=8,pady=8)
        ctk.CTkButton(bottom,text="Добавить",corner_radius=10,width=104,height=32,command=self.path_add_folder).pack(side="left",padx=2,pady=2)
        ctk.CTkButton(bottom,text="Действия",corner_radius=10,width=104,height=32,command=self.open_path_actions).pack(side="left",padx=(8,0),pady=2)
        ctk.CTkButton(bottom,text="Сохранить",corner_radius=10,width=110,height=32,command=self.path_apply).pack(side="right",padx=2,pady=2)

    def choose_path_scope(self):
        names={"user":"USER","machine":"MACHINE","both":"USER + MACHINE"}
        def set_scope(value):
            self.path_scope.set(value)
            self.path_scope_label.configure(text=f"Область: {names[value]}")
            self.path_reload()
        self._show_actions("Область PATH","Выбери, какие переменные PATH отобразить и сохранить.",[("USER",lambda:set_scope("user"),False),("MACHINE",lambda:set_scope("machine"),False),("USER + MACHINE",lambda:set_scope("both"),True)])

    def edit_path_filter(self):
        value=self._ask_value("Поиск в PATH","Введите часть пути. Оставь поле пустым, чтобы показать весь список.",self.path_search_var.get(),False,"Применить")
        if value is None:
            return
        self.path_search_var.set(value.strip())
        self.path_filter_label.configure(text="Фильтр: "+self._compact_value(value,"не задан"))
        self.path_rebuild()

    def path_load(self):
        scope=self.path_scope.get()
        if scope=="user":
            return read_path("user")
        if scope=="machine":
            return read_path("machine")
        user_items=read_path("user")
        machine_items=read_path("machine")
        out=[]
        seen=set()
        for p in user_items+machine_items:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def path_reload(self):
        if not hasattr(self,"path_tree"):
            return
        def worker():
            return self.path_load()
        def done(items):
            self._path_items=list(items)
            self.path_rebuild()
            self.status_var.set("PATH обновлён")
        self._run_worker("PATH",worker,done)

    def path_schedule_rebuild(self):
        try:
            if self._path_filter_after is not None:
                self.after_cancel(self._path_filter_after)
        except Exception:
            pass
        self._path_filter_after=self.after(120,self.path_rebuild)

    def path_rebuild(self):
        if not hasattr(self,"path_tree"):
            return
        self._path_iid_to_path.clear()
        self.path_tree.delete(*self.path_tree.get_children())
        counts=Counter(self._path_items)
        flt=(self.path_search_var.get() or "").strip().lower()
        n=0
        for index,p in enumerate(self._path_items):
            if flt and flt not in p.lower():
                continue
            dup=counts[p]>1
            status="DUP" if dup else "OK"
            tag="duplicate" if dup else "valid"
            iid=f"path_{index}_{n}"
            self.path_tree.insert("","end",iid=iid,values=(status,p),tags=(tag,))
            self._path_iid_to_path[iid]=p
            n+=1
        if hasattr(self,"status_var"):
            self.status_var.set(f"PATH: показано {n} из {len(self._path_items)}")

    def path_context_menu(self,event):
        iid=self.path_tree.identify_row(event.y)
        if iid:
            self.path_tree.selection_set(iid)
        menu=tk.Menu(self,tearoff=0,bg=self.CARD,fg=self.TEXT,activebackground=self.CARD_2,activeforeground=self.TEXT)
        menu.add_command(label="Редактировать",command=self.path_edit_selected)
        menu.add_command(label="Удалить",command=self.path_delete_selected)
        try:
            menu.tk_popup(event.x_root,event.y_root)
        finally:
            menu.grab_release()

    def path_edit_selected(self):
        selected=self._selected_path_values()
        if not selected:
            self.toast_fail("PATH","Выбери путь")
            return
        self.path_edit(selected[0])

    def path_row_menu(self,p):
        self.path_edit(p)

    def path_add_folder(self):
        from tkinter import filedialog
        d=filedialog.askdirectory(parent=self,title="Выберите папку для PATH")
        if not d:
            return
        self._path_items=add_path_once(self._path_items,d)
        self.path_rebuild()
        self.toast_ok("PATH","Путь добавлен в список")

    def path_edit(self,p):
        dlg=BigEditDialog(self,self._theme_dict(),"Редактирование пути PATH","PathItem",p,False)
        self.wait_window(dlg)
        if not dlg.result:
            return
        _name,new_val=dlg.result
        new_val=(new_val or "").strip().splitlines()[0].strip()
        if not new_val:
            return
        try:
            idx=self._path_items.index(p)
            self._path_items[idx]=new_val
            self.path_rebuild()
            self.toast_ok("PATH","Путь обновлён")
        except ValueError:
            pass

    def path_delete_selected(self):
        selected=self._selected_path_values()
        if not selected:
            self.toast_fail("PATH","Нечего удалять")
            return
        if not self._confirm("Удалить пути",f"Будет удалено выбранных путей: {len(selected)}. Изменения пока не сохранены в Windows.","Удалить"):
            return
        selected_set=set(selected)
        before=len(self._path_items)
        self._path_items=[p for p in self._path_items if p not in selected_set]
        self.path_rebuild()
        self.toast_ok("PATH",f"Удалено: {before-len(self._path_items)}")

    def path_dedup(self):
        if not self._confirm("Удалить дубликаты","Дублирующиеся элементы будут удалены из текущего списка PATH.","Удалить"):
            return
        before=len(self._path_items)
        self._path_items=dedup_keep_first(self._path_items)
        self.path_rebuild()
        self.toast_ok("PATH",f"Удалено дубликатов: {before-len(self._path_items)}")

    def path_prune(self):
        if not self._confirm("Проверить пути","Несуществующие элементы будут удалены из текущего списка PATH.","Проверить"):
            return
        items=list(self._path_items)
        def worker():
            pruned=prune_nonexistent(items)
            return pruned,len(items)-len(pruned)
        def done(result):
            pruned,removed=result
            self._path_items=pruned
            self.path_rebuild()
            self.toast_ok("PATH",f"Удалено несуществующих: {removed}")
        self._run_worker("PATH",worker,done)

    def path_apply(self):
        scope=self.path_scope.get()
        items=list(self._path_items)
        if not self._confirm("Сохранить PATH",f"Изменения будут записаны в область: {scope.upper()}.","Сохранить"):
            return
        def worker():
            if scope=="user":
                write_path("user",items)
                return "Сохранено: USER"
            if scope=="machine":
                if not is_admin():
                    raise PermissionError("Для MACHINE нужны админ-права")
                write_path("machine",items)
                return "Сохранено: MACHINE"
            write_path("user",items)
            if is_admin():
                write_path("machine",items)
                return "Сохранено: USER + MACHINE"
            return "Сохранено: USER. MACHINE требует админ-права"
        def done(text):
            self.toast_ok("PATH",text)
        def fail(text):
            self.toast_fail("PATH",text)
        self._run_worker("PATH",worker,done,fail,exclusive=True)

    def _build_tab_env(self):
        root=ctk.CTkFrame(self.tab_env,fg_color=self.BG,corner_radius=0)
        root._is_root_bg=True
        root.pack(fill="both",expand=True,padx=4,pady=0)
        root.grid_rowconfigure(1,weight=1)
        root.grid_columnconfigure(0,weight=1)
        self.sf_by_tab["Переменные среды"]=None
        self.env_scope=ctk.StringVar(value="user")
        self.env_search_var=ctk.StringVar(value="")
        self._env_data=[]
        self._env_iid_to_item={}
        self._env_filter_after=None
        self._configure_tree_style()

        top=self._card(root)
        top.grid(row=0,column=0,sticky="ew",padx=8,pady=8)
        top.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(top,text="Переменные среды",font=self._font(20,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=18,pady=(16,0))
        self.env_scope_label=ctk.CTkLabel(top,text="Область: USER",font=self._font(11,"bold"),text_color=self.ACCENT_3)
        self.env_scope_label.grid(row=1,column=0,sticky="w",padx=18,pady=(2,16))
        self.env_filter_label=ctk.CTkLabel(top,text="Фильтр не задан",font=self._font(11),text_color=self.MUTED)
        self.env_filter_label.grid(row=1,column=1,sticky="e",padx=(8,12),pady=(2,16))
        ctk.CTkButton(top,text="Область",width=88,height=32,corner_radius=10,command=self.choose_env_scope).grid(row=0,column=1,sticky="e",padx=(8,8),pady=16)
        ctk.CTkButton(top,text="Поиск",width=78,height=32,corner_radius=10,fg_color=self.CARD_2,hover_color=self.BORDER,command=self.edit_env_filter).grid(row=0,column=2,sticky="e",padx=(0,18),pady=16)

        self.env_list=self._card(root)
        self.env_list.grid(row=1,column=0,sticky="nsew",padx=8,pady=8)
        self.env_list.grid_rowconfigure(1,weight=1)
        self.env_list.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(self.env_list,text="Список переменных",font=self._font(14,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=14,pady=(12,6))
        wrap=tk.Frame(self.env_list,bg=self.CARD)
        wrap.grid(row=1,column=0,sticky="nsew",padx=14,pady=(0,14))
        wrap.grid_rowconfigure(0,weight=1)
        wrap.grid_columnconfigure(0,weight=1)
        self.env_tree=ttk.Treeview(wrap,columns=("scope","name","value"),show="headings",selectmode="browse",style="Mahashe.Treeview")
        self.env_tree.heading("scope",text="Область")
        self.env_tree.heading("name",text="Имя")
        self.env_tree.heading("value",text="Значение")
        self.env_tree.column("scope",width=100,minwidth=80,anchor="center",stretch=False)
        self.env_tree.column("name",width=220,minwidth=140,anchor="w",stretch=False)
        self.env_tree.column("value",width=720,minwidth=260,anchor="w",stretch=True)
        ybar=ttk.Scrollbar(wrap,orient="vertical",command=self.env_tree.yview)
        xbar=ttk.Scrollbar(wrap,orient="horizontal",command=self.env_tree.xview)
        self.env_tree.configure(yscrollcommand=ybar.set,xscrollcommand=xbar.set)
        self.env_tree.grid(row=0,column=0,sticky="nsew")
        ybar.grid(row=0,column=1,sticky="ns")
        xbar.grid(row=1,column=0,sticky="ew")
        self.env_tree.tag_configure("user",foreground=self.ACCENT_1)
        self.env_tree.tag_configure("machine",foreground=self.ACCENT_2)
        self.env_tree.bind("<Double-Button-1>",lambda _e:self.env_edit_selected())
        self.env_tree.bind("<Button-3>",self.env_context_menu)

        bottom=ctk.CTkFrame(root,fg_color=self.BG,corner_radius=0)
        bottom.grid(row=2,column=0,sticky="ew",padx=8,pady=8)
        ctk.CTkButton(bottom,text="Создать",corner_radius=10,width=94,height=32,command=self.env_create).pack(side="left",padx=2,pady=2)
        ctk.CTkButton(bottom,text="Действия",corner_radius=10,width=104,height=32,command=self.open_env_actions).pack(side="left",padx=(8,0),pady=2)
        ctk.CTkButton(bottom,text="Обновить",corner_radius=10,width=100,height=32,command=self.env_reload).pack(side="right",padx=2,pady=2)

    def choose_env_scope(self):
        names={"user":"USER","machine":"MACHINE","both":"USER + MACHINE"}
        def set_scope(value):
            self.env_scope.set(value)
            self.env_scope_label.configure(text=f"Область: {names[value]}")
            self.env_reload()
        self._show_actions("Область переменных","Выбери, какую область переменных среды отобразить.",[("USER",lambda:set_scope("user"),True),("MACHINE",lambda:set_scope("machine"),False),("USER + MACHINE",lambda:set_scope("both"),False)])

    def edit_env_filter(self):
        value=self._ask_value("Поиск переменных","Введите имя или часть значения. Оставь поле пустым, чтобы показать весь список.",self.env_search_var.get(),False,"Применить")
        if value is None:
            return
        self.env_search_var.set(value.strip())
        self.env_filter_label.configure(text="Фильтр: "+self._compact_value(value,"не задан"))
        self.env_rebuild()

    def env_reload(self,silent=False):
        if not hasattr(self,"env_tree"):
            return
        scope=self.env_scope.get()
        def worker():
            out=[]
            def load_one(sc):
                data=list_env(sc)
                for name,(value,vtype) in data.items():
                    out.append((sc,name,value,vtype))
            if scope in ("user","both"):
                load_one("user")
            if scope in ("machine","both"):
                load_one("machine")
            out.sort(key=lambda x:(x[1].lower(),x[0]))
            return out
        def done(data):
            self._env_data=list(data)
            self.env_rebuild()
            if not silent:
                self.status_var.set("Переменные среды обновлены")
        def fail(text):
            self.toast_fail("Переменные среды",f"Ошибка чтения: {text}")
        self._run_worker("Переменные среды",worker,done,fail)

    def env_schedule_rebuild(self):
        try:
            if self._env_filter_after is not None:
                self.after_cancel(self._env_filter_after)
        except Exception:
            pass
        self._env_filter_after=self.after(120,self.env_rebuild)

    def env_rebuild(self):
        if not hasattr(self,"env_tree"):
            return
        self._env_iid_to_item.clear()
        self.env_tree.delete(*self.env_tree.get_children())
        flt=(self.env_search_var.get() or "").strip().lower()
        n=0
        for index,(scope,name,value,vtype) in enumerate(self._env_data):
            if flt and flt not in name.lower() and flt not in (value or "").lower():
                continue
            short=(value or "").replace("\r"," ").replace("\n"," ")
            if len(short)>240:
                short=short[:240]+"…"
            iid=f"env_{index}_{n}"
            badge="USER" if scope=="user" else "MACHINE"
            tag="user" if scope=="user" else "machine"
            self.env_tree.insert("","end",iid=iid,values=(badge,name,short),tags=(tag,))
            self._env_iid_to_item[iid]=(scope,name,value,vtype)
            n+=1
        if hasattr(self,"status_var"):
            self.status_var.set(f"Переменные среды: показано {n} из {len(self._env_data)}")

    def env_context_menu(self,event):
        iid=self.env_tree.identify_row(event.y)
        if iid:
            self.env_tree.selection_set(iid)
        menu=tk.Menu(self,tearoff=0,bg=self.CARD,fg=self.TEXT,activebackground=self.CARD_2,activeforeground=self.TEXT)
        menu.add_command(label="Редактировать",command=self.env_edit_selected)
        menu.add_command(label="Удалить",command=self.env_delete_selected)
        try:
            menu.tk_popup(event.x_root,event.y_root)
        finally:
            menu.grab_release()

    def env_edit_selected(self):
        item=self._selected_env_item()
        if not item:
            self.toast_fail("Переменные среды","Выбери переменную")
            return
        scope,name,_value,_vtype=item
        self.env_edit_open(scope,name)

    def env_delete_selected(self):
        item=self._selected_env_item()
        if not item:
            self.toast_fail("Переменные среды","Выбери переменную")
            return
        scope,name,_value,_vtype=item
        self.env_delete(scope,name)

    def env_row_menu(self,scope,name):
        self.env_edit_open(scope,name)

    def _env_menu_edit(self,win,scope,name):
        try:
            win.destroy()
        except Exception:
            pass
        self.env_edit_open(scope,name)

    def _env_menu_delete(self,win,scope,name):
        try:
            win.destroy()
        except Exception:
            pass
        self.env_delete(scope,name)

    def env_create(self):
        dlg=BigEditDialog(self,self._theme_dict(),"Создать переменную среды","","",True)
        self.wait_window(dlg)
        if not dlg.result:
            return
        name,value=dlg.result
        scope=self.env_scope.get()
        def worker():
            if scope=="both":
                set_env("user",name,value)
                if is_admin():
                    set_env("machine",name,value)
                    return f"Создано: USER + MACHINE: {name}"
                return f"Создано: USER. MACHINE требует админ-права: {name}"
            if scope=="machine" and not is_admin():
                raise PermissionError("Для MACHINE нужны админ-права")
            set_env(scope,name,value)
            return f"Сохранено: {scope.upper()}: {name}"
        def done(text):
            self.toast_ok("Переменные среды",text)
            self.env_reload(silent=True)
        def fail(text):
            self.toast_fail("Переменные среды",text)
        self._run_worker("Переменные среды",worker,done,fail,exclusive=True)

    def env_edit_open(self,scope,name):
        cur=get_env(scope,name)
        if not cur:
            self.toast_fail("Переменные среды","Переменная не найдена")
            return
        value,_vtype=cur
        dlg=BigEditDialog(self,self._theme_dict(),f"Редактирование переменной ({scope.upper()})",name,value,False)
        self.wait_window(dlg)
        if not dlg.result:
            return
        _name,new_value=dlg.result
        def worker():
            if scope=="machine" and not is_admin():
                raise PermissionError("Для MACHINE нужны админ-права")
            set_env(scope,name,new_value)
            return f"Сохранено: {scope.upper()}: {name}"
        def done(text):
            self.toast_ok("Переменные среды",text)
            self.env_reload(silent=True)
        def fail(text):
            self.toast_fail("Переменные среды",text)
        self._run_worker("Переменные среды",worker,done,fail,exclusive=True)

    def env_delete(self,scope,name):
        if not self._confirm("Удалить переменную",f"Переменная {name} будет удалена из области {scope.upper()}.","Удалить"):
            return
        def worker():
            if scope=="machine" and not is_admin():
                raise PermissionError("Для MACHINE нужны админ-права")
            delete_env(scope,name)
            return f"Удалено: {scope.upper()}: {name}"
        def done(text):
            self.toast_ok("Переменные среды",text)
            self.env_reload(silent=True)
        def fail(text):
            self.toast_fail("Переменные среды",text)
        self._run_worker("Переменные среды",worker,done,fail,exclusive=True)

    def _build_tab_icons(self):
        sf=self._scrollable(self.tab_icons)
        self.sf_by_tab["Иконки"]=sf
        self.icon_vars={
            "c":ctk.StringVar(value=""),
            "drive":ctk.StringVar(value=""),
            "removable":ctk.StringVar(value=""),
            "folder":ctk.StringVar(value=""),
            "desktop":ctk.StringVar(value=""),
            "documents":ctk.StringVar(value=""),
            "pictures":ctk.StringVar(value=""),
            "videos":ctk.StringVar(value=""),
        }
        self.icon_summary_labels={}
        hero=self._card(sf)
        hero.pack(fill="x",padx=8,pady=8)
        hero.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(hero,text="Системные иконки",font=self._font(20,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=18,pady=(18,2))
        ctk.CTkLabel(hero,text="Выбери .ico в файловом окне — путь появится только как краткое состояние, без строк ввода.",font=self._font(12),text_color=self.MUTED).grid(row=1,column=0,sticky="w",padx=18,pady=(0,16))
        groups=[("Диски",[("c","Диск C:"),("drive","Остальные диски"),("removable","Съёмные носители")]),("Папки",[("folder","Все папки"),("desktop","Рабочий стол"),("documents","Документы"),("pictures","Изображения"),("videos","Видео")])]
        for title,items in groups:
            card=self._card(sf)
            card.pack(fill="x",padx=8,pady=(0,8))
            ctk.CTkLabel(card,text=title,font=self._font(14,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=14,pady=(14,10))
            for row,(key,label) in enumerate(items,start=1):
                self.icon_summary_labels[key]=self._choice_button(card,row,label,"Иконка не выбрана",lambda k=key:self.pick_ico(self.icon_vars[k],k),"Выбрать")
        footer=self._card(sf)
        footer.pack(fill="x",padx=8,pady=(0,8))
        footer.grid_columnconfigure(0,weight=1)
        ctk.CTkButton(footer,text="Действия",width=104,height=34,corner_radius=10,fg_color=self.CARD_2,hover_color=self.BORDER,command=self.open_icons_actions).grid(row=0,column=1,sticky="e",padx=16,pady=14)
        ctk.CTkButton(footer,text="Применить",width=108,height=34,corner_radius=10,command=self.apply_icons_ui).grid(row=0,column=2,sticky="e",padx=(0,16),pady=14)


    def pick_ico(self,var,key):
        from tkinter import filedialog
        p=filedialog.askopenfilename(parent=self,title="Выберите иконку",filetypes=[("Icon","*.ico"),("All files","*.*")])
        if not p:
            return
        var.set(p)
        self._set_icon_summary(key)


    def apply_icons_ui(self):
        if not is_windows():
            self.toast_fail("Ошибка","Это работает только на Windows")
            return
        specs={}
        if self.icon_vars["c"].get().strip():
            specs[ICON_DRIVE_C]=self.icon_vars["c"].get().strip()
        if self.icon_vars["drive"].get().strip():
            specs[ICON_DRIVE_GENERIC]=self.icon_vars["drive"].get().strip()
        if self.icon_vars["removable"].get().strip():
            specs[ICON_REMOVABLE]=self.icon_vars["removable"].get().strip()
        if self.icon_vars["folder"].get().strip():
            specs[ICON_FOLDER]=self.icon_vars["folder"].get().strip()
        if self.icon_vars["desktop"].get().strip():
            specs[CLSID_DESKTOP]=self.icon_vars["desktop"].get().strip()
        if self.icon_vars["documents"].get().strip():
            specs[CLSID_DOCUMENTS]=self.icon_vars["documents"].get().strip()
        if self.icon_vars["pictures"].get().strip():
            specs[CLSID_PICTURES]=self.icon_vars["pictures"].get().strip()
        if self.icon_vars["videos"].get().strip():
            specs[CLSID_VIDEOS]=self.icon_vars["videos"].get().strip()
        if not specs:
            self.toast_fail("Ошибка","Не задано ни одной иконки")
            return
        if not self._confirm("Применить иконки",f"Будет изменено системных назначений: {len(specs)}.","Применить"):
            return
        def worker():
            apply_icons(specs)
            return "Применено"
        def done(text):
            self.toast_ok("Иконки",text)
        def fail(text):
            self.toast_fail("Иконки",text or "Не удалось применить иконки")
        self._run_worker("Иконки",worker,done,fail,exclusive=True)

    def refresh_icons(self):
        def worker():
            ie4uinit_clear_icon_cache()
            sh_change_notify()
            return "Команда обновления отправлена"
        def done(text):
            self.toast_ok("Иконки",text)
        self._run_worker("Иконки",worker,done)

    def _build_tab_opt(self):
        sf=self._scrollable(self.tab_opt)
        self.sf_by_tab["Оптимизация"]=sf
        self.opt_exe_path_var=ctk.StringVar(value="")
        self.opt_cpu_var=ctk.StringVar(value="Высокий")
        self.opt_gpu_var=ctk.BooleanVar(value=True)
        self.opt_games_var=ctk.BooleanVar(value=True)
        hero=self._card(sf)
        hero.pack(fill="x",padx=8,pady=8)
        hero.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(hero,text="Оптимизация процессов",font=self._font(20,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=18,pady=(18,2))
        self.opt_summary_label=ctk.CTkLabel(hero,text="Программа не выбрана",font=self._font(12),text_color=self.MUTED,anchor="w")
        self.opt_summary_label.grid(row=1,column=0,sticky="ew",padx=18,pady=(0,16))
        ctk.CTkButton(hero,text="Настроить",width=108,height=34,corner_radius=10,command=self.open_opt_config_dialog).grid(row=0,column=1,rowspan=2,sticky="e",padx=18,pady=18)
        actions=self._card(sf)
        actions.pack(fill="x",padx=8,pady=(0,8))
        actions.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(actions,text="Настройки применяются только после явного подтверждения.",font=self._font(12),text_color=self.MUTED).grid(row=0,column=0,sticky="w",padx=16,pady=14)
        ctk.CTkButton(actions,text="Действия",width=104,height=34,corner_radius=10,fg_color=self.CARD_2,hover_color=self.BORDER,command=self.open_opt_actions).grid(row=0,column=1,sticky="e",padx=(0,8),pady=14)
        ctk.CTkButton(actions,text="Применить",width=108,height=34,corner_radius=10,command=self.apply_opt).grid(row=0,column=2,sticky="e",padx=(0,16),pady=14)

        self.opt_list_container=ctk.CTkFrame(sf,fg_color=self.BG,corner_radius=0)
        self.opt_list_container.pack(fill="both",expand=True,padx=0,pady=0)

        self.refresh_opt_list()

    def open_opt_config_dialog(self):
        win=ctk.CTkToplevel(self)
        win.title("Настройка процесса")
        win.geometry("560x400")
        win.resizable(False,False)
        win.configure(fg_color=self.BG)
        win.transient(self)
        win.grab_set()
        card=ctk.CTkFrame(win,fg_color=self.CARD,corner_radius=18,border_width=1,border_color=self.BORDER)
        card.pack(fill="both",expand=True,padx=14,pady=14)
        card.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(card,text="Настройка процесса",font=self._font(18,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=18,pady=(16,4))
        ctk.CTkLabel(card,text="Исполняемый файл задаётся здесь, а не на главной странице раздела.",font=self._font(12),text_color=self.MUTED).grid(row=1,column=0,sticky="w",padx=18,pady=(0,12))
        exe_row=ctk.CTkFrame(card,fg_color="transparent",corner_radius=0)
        exe_row.grid(row=2,column=0,sticky="ew",padx=18,pady=(0,12))
        exe_row.grid_columnconfigure(0,weight=1)
        entry=ctk.CTkEntry(exe_row,textvariable=self.opt_exe_path_var,height=38,corner_radius=10,border_width=1,border_color=self.BORDER,fg_color=self.CARD_2,text_color=self.TEXT)
        entry.grid(row=0,column=0,sticky="ew",padx=(0,8))
        ctk.CTkButton(exe_row,text="Выбрать",width=92,height=38,corner_radius=10,command=lambda:self.pick_opt_exe(win)).grid(row=0,column=1)
        ctk.CTkLabel(card,text="Приоритет CPU",font=self._font(12,"bold"),text_color=self.TEXT).grid(row=3,column=0,sticky="w",padx=18,pady=(0,6))
        ctk.CTkOptionMenu(card,values=[n for n,_ in CPU_CHOICES],variable=self.opt_cpu_var,width=220,height=36,corner_radius=10).grid(row=4,column=0,sticky="w",padx=18,pady=(0,12))
        ctk.CTkCheckBox(card,text="GPU: High Performance при полном пути",variable=self.opt_gpu_var,font=self._font(12)).grid(row=5,column=0,sticky="w",padx=18,pady=(0,8))
        ctk.CTkCheckBox(card,text="Применять Games профиль",variable=self.opt_games_var,font=self._font(12)).grid(row=6,column=0,sticky="w",padx=18,pady=(0,12))
        buttons=ctk.CTkFrame(card,fg_color="transparent",corner_radius=0)
        buttons.grid(row=7,column=0,sticky="ew",padx=18,pady=(0,16))
        buttons.grid_columnconfigure(0,weight=1)
        ctk.CTkButton(buttons,text="Отмена",width=104,height=34,corner_radius=10,fg_color=self.CARD_2,hover_color=self.BORDER,command=win.destroy).grid(row=0,column=0,sticky="w")
        ctk.CTkButton(buttons,text="Сохранить",width=114,height=34,corner_radius=10,command=lambda:self._save_opt_config(win)).grid(row=0,column=1,sticky="e")
        win.update_idletasks()
        w=win.winfo_width()
        h=win.winfo_height()
        win.geometry(f"{w}x{h}+{(win.winfo_screenwidth()-w)//2}+{(win.winfo_screenheight()-h)//2}")

    def _save_opt_config(self,win):
        raw=(self.opt_exe_path_var.get() or "").strip().strip('"')
        if not raw:
            self.toast_fail("Оптимизация","Укажи .exe в диалоговом окне")
            return
        self.opt_exe_path_var.set(raw)
        self.opt_summary_label.configure(text=f"{normalize_exe_name(raw)} · {self.opt_cpu_var.get()} · GPU {'вкл' if self.opt_gpu_var.get() else 'выкл'}")
        win.destroy()


    def pick_opt_exe(self,parent=None):
        from tkinter import filedialog
        p=filedialog.askopenfilename(parent=parent or self,title="Выберите .exe",filetypes=[("Executable","*.exe"),("All files","*.*")])
        if not p:
            return
        self.opt_exe_path_var.set(p)
        if hasattr(self,"opt_summary_label"):
            self.opt_summary_label.configure(text=f"{normalize_exe_name(p)} · {self.opt_cpu_var.get()}")


    def _refresh_opt_list_body(self,items=None):
        for ch in self.opt_list_container.winfo_children():
            ch.destroy()
        card=self._card(self.opt_list_container)
        card.pack(fill="x",padx=8,pady=8)
        card.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(card,text="Уже добавленные процессы:",font=ctk.CTkFont(size=14,weight="bold")).grid(row=0,column=0,sticky="w",padx=14,pady=(12,6))
        if items is None:
            try:
                items=enum_ifeo_cpu_priority() if is_windows() else []
            except Exception:
                log_error(f"enum_ifeo_cpu_priority error: {traceback.format_exc()}")
                items=[]
        if not items:
            ctk.CTkLabel(card,text="Пока пусто.",justify="left").grid(row=1,column=0,sticky="w",padx=14,pady=(0,12))
            return
        r=1
        for it in items[:200]:
            exe=it.get("exe") or ""
            v=int(it.get("value",0))
            nm=CPU_NAME_BY_VAL.get(v,str(v))
            line=f"{exe}  —  {nm} ({v})"
            rowf=ctk.CTkFrame(card,fg_color=self.CARD,corner_radius=0)
            rowf.grid(row=r,column=0,sticky="ew",padx=14,pady=(0,6))
            rowf.grid_columnconfigure(0,weight=1)
            ctk.CTkLabel(rowf,text=line,anchor="w").grid(row=0,column=0,sticky="w",padx=(0,10),pady=4)
            ctk.CTkButton(rowf,text="Удалить",corner_radius=13,width=78,height=30,command=lambda e=exe:self._opt_delete_from_list(e)).grid(row=0,column=1,sticky="e",pady=4)
            r+=1

    def _opt_fill_from_list(self,exe):
        self.opt_exe_path_var.set(exe)
        try:
            v=reg_get_value(winreg.HKEY_LOCAL_MACHINE,IFEO_BASE+"\\"+exe+r"\PerfOptions","CpuPriorityClass",None)
            if v is not None:
                vi=int(v)
                nm=CPU_NAME_BY_VAL.get(vi)
                if nm:
                    self.opt_cpu_var.set(nm)
        except Exception:
            pass
        self.toast_ok("Оптимизация","Подставлено из списка")


    def _opt_delete_from_list(self,exe):
        self.opt_exe_path_var.set(exe)
        self.delete_opt()


    def apply_opt(self):
        if not is_windows():
            self.toast_fail("Ошибка","Это работает только на Windows")
            return
        raw=(self.opt_exe_path_var.get() or "").strip().strip('"')
        if not raw:
            self.toast_fail("Ошибка","Пустое поле .exe")
            return
        exe_name=normalize_exe_name(raw)
        cpu_name=self.opt_cpu_var.get()
        cpu_val=CPU_VAL_BY_NAME.get(cpu_name,3)
        want_gpu=bool(self.opt_gpu_var.get())
        want_games=bool(self.opt_games_var.get())
        full_path=None
        if raw.lower().endswith(".exe") and os.path.isabs(raw) and os.path.isfile(raw):
            full_path=os.path.abspath(raw)
        elif raw.lower().endswith(".exe") and os.path.isabs(raw):
            full_path=os.path.abspath(raw)
        if not self._confirm("Применить оптимизацию",f"Будет настроен приоритет для {exe_name}.","Применить"):
            return
        def worker():
            set_ifeo_cpu_priority(exe_name,cpu_val)
            gpu_ok=False
            if want_gpu and full_path:
                try:
                    gpu_ok=set_gpu_high_perf(full_path)
                except Exception:
                    gpu_ok=False
            if want_games:
                try:
                    apply_games_profile()
                except PermissionError:
                    pass
            if want_gpu and not full_path:
                return f"{exe_name}: CpuPriorityClass записан. GPU-предпочтение требует полный путь."
            if want_gpu and full_path and not gpu_ok:
                return f"{exe_name}: CpuPriorityClass записан. GPU-pref не удалось записать."
            return f"{exe_name}: настройки применены."
        def done(text):
            self.refresh_opt_list()
            self.toast_ok("Готово",text)
        def fail(text):
            self.toast_fail("Оптимизация",text or "Не удалось применить настройки")
        self._run_worker("Оптимизация",worker,done,fail,exclusive=True)

    def delete_opt(self):
        if not is_windows():
            self.toast_fail("Ошибка","Это работает только на Windows")
            return
        raw=(self.opt_exe_path_var.get() or "").strip().strip('"')
        if not raw:
            self.toast_fail("Ошибка","Пустое поле .exe")
            return
        exe_name=normalize_exe_name(raw)
        full_path=None
        if raw.lower().endswith(".exe") and os.path.isabs(raw):
            full_path=os.path.abspath(raw)
        if not self._confirm("Удалить оптимизацию",f"Настройки приоритета для {exe_name} будут удалены.","Удалить"):
            return
        def worker():
            ok=delete_ifeo_cpu_priority(exe_name)
            if full_path:
                try:
                    delete_gpu_pref(full_path)
                except Exception:
                    pass
            return exe_name if ok else f"{exe_name}: флаг не найден"
        def done(text):
            self.refresh_opt_list()
            self.toast_ok("Удалено",text)
        def fail(text):
            self.toast_fail("Оптимизация",text or "Не удалось удалить CpuPriorityClass")
        self._run_worker("Оптимизация",worker,done,fail,exclusive=True)

    def _open_url(self,url):
        try:
            webbrowser.open_new_tab(url)
            self.status_var.set(f"Открыта ссылка: {url}")
        except Exception as e:
            self.toast_fail("Ссылка",str(e) or "Не удалось открыть браузер")

    def open_developer_site(self):
        self._open_url("https://profile.mahashe.org/")

    def open_developer_github(self):
        self._open_url("https://github.com/MahasheDev")

    def open_donate(self):
        self._open_url("https://boosty.to/mahashedev")

    def _home_action_tile(self,parent,column,icon,title,text,command,accent=False):
        tile=self._card(parent,corner_radius=16)
        tile.grid(row=0,column=column,sticky="nsew",padx=4,pady=4)
        tile.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(tile,text=icon,font=self._font(24,"bold"),text_color=self.ACCENT_2 if accent else self.ACCENT_1).grid(row=0,column=0,sticky="w",padx=16,pady=(16,4))
        ctk.CTkLabel(tile,text=title,font=self._font(14,"bold"),text_color=self.TEXT).grid(row=1,column=0,sticky="w",padx=16,pady=(0,2))
        ctk.CTkLabel(tile,text=text,font=self._font(11),text_color=self.MUTED,justify="left",wraplength=210).grid(row=2,column=0,sticky="w",padx=16,pady=(0,14))
        button=ctk.CTkButton(tile,text="Открыть",height=34,corner_radius=10,command=command)
        if accent:
            button.configure(fg_color=self.ACCENT_1,hover_color=self.ACCENT_2,text_color=self.BG)
        button.grid(row=3,column=0,sticky="ew",padx=16,pady=(0,16))

    def _build_tab_home(self):
        sf=self._scrollable(self.tab_home)
        self.sf_by_tab["Главная"]=sf
        ctk.CTkLabel(sf,text="Быстрый доступ",font=self._font(16,"bold"),text_color=self.TEXT).pack(anchor="w",padx=12,pady=(12,4))
        ctk.CTkLabel(sf,text="Выбери раздел для настройки Windows. Изменения выполняются только после подтверждения.",font=self._font(12),text_color=self.MUTED).pack(anchor="w",padx=12,pady=(0,10))
        rows=[
            ("Папки Windows","Расположения системных пользовательских папок.","Открыть",lambda:self.show_page("Папки")),
            ("TEMP и TMP","Временные директории пользователя и системы.","Открыть",lambda:self.show_page("TEMP")),
            ("PATH","Список путей пользователя и системы.","Открыть",lambda:self.show_page("Path")),
            ("Переменные среды","Создание и редактирование переменных окружения.","Открыть",lambda:self.show_page("Переменные среды")),
            ("Иконки","Настройка системных иконок.","Открыть",lambda:self.show_page("Иконки")),
            ("Оптимизация","Приоритеты процессов и GPU-предпочтения.","Открыть",lambda:self.show_page("Оптимизация")),
        ]
        for title,description,button,command in rows:
            card=self._card(sf)
            card.pack(fill="x",padx=8,pady=5)
            card.grid_columnconfigure(0,weight=1)
            ctk.CTkLabel(card,text=title,font=self._font(14,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=14,pady=(11,1))
            ctk.CTkLabel(card,text=description,font=self._font(12),text_color=self.MUTED).grid(row=1,column=0,sticky="w",padx=14,pady=(0,11))
            ctk.CTkButton(card,text=button,width=112,height=34,corner_radius=15,command=command).grid(row=0,column=1,rowspan=2,sticky="e",padx=14,pady=10)
        links=self._card(sf)
        links.pack(fill="x",padx=8,pady=(8,5))
        links.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(links,text="Ссылки",font=self._font(14,"bold"),text_color=self.TEXT).grid(row=0,column=0,sticky="w",padx=14,pady=12)
        ctk.CTkButton(links,text="Сайт",width=94,height=34,corner_radius=15,command=self.open_developer_site).grid(row=0,column=1,padx=(6,4),pady=10)
        ctk.CTkButton(links,text="GitHub",width=94,height=34,corner_radius=15,command=self.open_developer_github).grid(row=0,column=2,padx=4,pady=10)
        ctk.CTkButton(links,text="Поддержать",width=122,height=34,corner_radius=15,command=self.open_donate).grid(row=0,column=3,padx=(4,14),pady=10)


if __name__=="__main__":
    elevate_if_needed()
    ui=load_ui_settings()
    with open(LOG_PATH,"a",encoding="utf-8") as f:
        f.write(f"==== {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')} START ====\n")
    App(ui).mainloop()
