import os
import sys
import struct
import threading
import hashlib
import tempfile
from pathlib import Path

try:
    from pydub import AudioSegment
    from pydub.effects import normalize
except ImportError:
    print("pip install pydub")
    sys.exit(1)

try:
    import tkinter as tk
    from tkinter import filedialog, ttk, messagebox
except ImportError:
    print("Tkinter не найден!")
    sys.exit(1)

try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
    HAS_PYGAME = True
except Exception:
    HAS_PYGAME = False


# ══════════════════════════════════════════════════════════════
#  SONIFICATION ENGINE — байты → звук, без компромиссов
# ══════════════════════════════════════════════════════════════

class SonifyEngine:
    """Движок: читает ЛЮБОЙ файл как сырой звук — что есть, то и звучит"""

    SAMPLE_RATES = [2000, 4000, 8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000]
    CHANNELS = [1, 2]
    BIT_DEPTHS = {8: 1, 16: 2, 24: 3, 32: 4}
    EXPORT_FORMATS = ['wav', 'mp3', 'ogg', 'flac']
    BITRATES = ['64k', '96k', '128k', '192k', '256k', '320k']

    PRESETS = {
        'Raw Standard':     {'frame_rate': 44100, 'channels': 1, 'sample_width': 2},
        'Lo-Fi Glitch':     {'frame_rate': 8000,  'channels': 1, 'sample_width': 1},
        'Deep Drone':       {'frame_rate': 4000,  'channels': 1, 'sample_width': 2},
        'Stereo Chaos':     {'frame_rate': 44100, 'channels': 2, 'sample_width': 2},
        'Crispy 8-bit':     {'frame_rate': 22050, 'channels': 1, 'sample_width': 1},
        'HQ Raw':           {'frame_rate': 48000, 'channels': 2, 'sample_width': 2},
        'Ultra Slow':       {'frame_rate': 2000,  'channels': 1, 'sample_width': 1},
        'Alien Signal':     {'frame_rate': 11025, 'channels': 2, 'sample_width': 1},
        'Bass Rumble':      {'frame_rate': 8000,  'channels': 1, 'sample_width': 4},
        'Broken Radio':     {'frame_rate': 16000, 'channels': 1, 'sample_width': 2},
        'Hi-Res Glitch':    {'frame_rate': 96000, 'channels': 2, 'sample_width': 3},
        'Tape Warp':        {'frame_rate': 32000, 'channels': 1, 'sample_width': 2},
        'Micro Grain':      {'frame_rate': 2000,  'channels': 2, 'sample_width': 2},
        'Digital Scream':   {'frame_rate': 44100, 'channels': 1, 'sample_width': 1},
    }

    @staticmethod
    def read_file_raw(file_path):
        """Читаем ВСЕ байты файла — без исключений"""
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            if not data:
                # Пустой файл — генерируем тишину
                data = b'\x00' * 1024
            return data
        except PermissionError:
            # Нет доступа — возвращаем паттерн ошибки как звук
            return b'\xDE\xAD' * 512
        except Exception:
            return b'\xFF\x00' * 512

    @staticmethod
    def bytes_to_audio(raw_bytes, frame_rate=44100, channels=1, sample_width=2):
        """
        Сырые байты → PCM аудио
        НИКАКОЙ обработки — что пришло, то и звучит
        """
        block_align = sample_width * channels

        # Гарантируем минимум данных
        if len(raw_bytes) < block_align:
            raw_bytes = raw_bytes + b'\x00' * (block_align - len(raw_bytes))

        # Выравниваем
        trimmed_len = (len(raw_bytes) // block_align) * block_align
        if trimmed_len == 0:
            trimmed_len = block_align
            raw_bytes = raw_bytes[:block_align].ljust(block_align, b'\x00')

        audio_data = raw_bytes[:trimmed_len]

        try:
            audio = AudioSegment(
                data=audio_data,
                sample_width=sample_width,
                frame_rate=frame_rate,
                channels=channels,
            )
        except Exception:
            # Фоллбэк — самый безопасный формат
            block_align = 1
            trimmed_len = len(raw_bytes)
            audio = AudioSegment(
                data=raw_bytes[:trimmed_len],
                sample_width=1,
                frame_rate=44100,
                channels=1,
            )

        return audio

    @staticmethod
    def sonify(file_path, frame_rate=44100, channels=1, sample_width=2,
               offset=0, length=None):
        """Файл → сырой звук. Точка."""
        raw = SonifyEngine.read_file_raw(file_path)

        if offset > 0:
            raw = raw[offset:]
        if length and length > 0:
            raw = raw[:length]

        if not raw:
            raw = b'\x00' * (sample_width * channels * frame_rate)  # 1 сек тишины

        return SonifyEngine.bytes_to_audio(raw, frame_rate, channels, sample_width)

    @staticmethod
    def sonify_with_effects(file_path, params, effects=None):
        """Sonify + эффекты (эффекты опциональны)"""
        audio = SonifyEngine.sonify(
            file_path,
            frame_rate=params.get('frame_rate', 44100),
            channels=params.get('channels', 1),
            sample_width=params.get('sample_width', 2),
            offset=params.get('offset', 0),
            length=params.get('length', None),
        )

        if effects:
            audio = SonifyEngine.apply_effects(audio, effects)

        return audio

    @staticmethod
    def apply_effects(audio, effects):
        """Цепочка эффектов — каждый безопасно обёрнут"""
        result = audio

        try:
            if effects.get('normalize', False):
                result = normalize(result)
        except Exception:
            pass

        try:
            gain = effects.get('gain_db', 0)
            if gain != 0:
                result = result + gain
        except Exception:
            pass

        try:
            fade_in = effects.get('fade_in_ms', 0)
            if fade_in > 0:
                result = result.fade_in(min(fade_in, len(result)))
        except Exception:
            pass

        try:
            fade_out = effects.get('fade_out_ms', 0)
            if fade_out > 0:
                result = result.fade_out(min(fade_out, len(result)))
        except Exception:
            pass

        try:
            if effects.get('reverse', False):
                result = result.reverse()
        except Exception:
            pass

        try:
            speed = effects.get('speed', 1.0)
            if speed != 1.0 and 0.05 <= speed <= 20.0:
                orig_rate = result.frame_rate
                new_rate = max(100, int(orig_rate * speed))
                result = result._spawn(result.raw_data, overrides={
                    "frame_rate": new_rate
                }).set_frame_rate(orig_rate)
        except Exception:
            pass

        try:
            trim_start = effects.get('trim_start_sec', 0)
            trim_end = effects.get('trim_end_sec', 0)
            if trim_start > 0:
                ms = int(trim_start * 1000)
                if ms < len(result):
                    result = result[ms:]
            if trim_end > 0:
                ms = int(trim_end * 1000)
                if ms < len(result):
                    result = result[:ms]
        except Exception:
            pass

        try:
            repeat = effects.get('repeat', 1)
            if isinstance(repeat, int) and 1 < repeat <= 50:
                result = result * repeat
        except Exception:
            pass

        return result

    @staticmethod
    def get_audio_info(audio):
        """Информация об аудио"""
        try:
            duration = len(audio) / 1000.0
            minutes = int(duration // 60)
            seconds = duration % 60
            try:
                dbfs = round(audio.dBFS, 2)
            except Exception:
                dbfs = -96.0
            return {
                'duration_sec': duration,
                'duration_str': f"{minutes:02d}:{seconds:05.2f}",
                'frame_rate': audio.frame_rate,
                'channels': audio.channels,
                'sample_width': audio.sample_width,
                'bits': audio.sample_width * 8,
                'rms': audio.rms,
                'dBFS': dbfs,
                'max_amplitude': audio.max,
                'frame_count': int(audio.frame_count()),
                'raw_size': len(audio.raw_data),
            }
        except Exception:
            return {
                'duration_sec': 0, 'duration_str': '00:00.00',
                'frame_rate': 0, 'channels': 0, 'sample_width': 0,
                'bits': 0, 'rms': 0, 'dBFS': -96.0,
                'max_amplitude': 0, 'frame_count': 0, 'raw_size': 0,
            }

    @staticmethod
    def get_file_info(file_path):
        """Информация о входном файле — безопасно для любого файла"""
        try:
            p = Path(file_path)
            size = os.path.getsize(file_path)
        except Exception:
            return {
                'name': str(file_path), 'ext': '', 'size': 0,
                'size_str': '0 B', 'type': 'Unknown', 'hash': '',
                'header_hex': '', 'header_ascii': '',
            }

        try:
            with open(file_path, 'rb') as f:
                header = f.read(64)
        except Exception:
            header = b''

        file_type = "Binary Data"
        magic_signatures = {
            b'\x89PNG':             'PNG Image',
            b'\xff\xd8\xff':        'JPEG Image',
            b'GIF8':                'GIF Image',
            b'BM':                  'BMP Image',
            b'PK':                  'ZIP/DOCX/APK',
            b'MZ':                  'EXE/DLL (PE)',
            b'\x7fELF':             'ELF Binary',
            b'%PDF':                'PDF Document',
            b'Rar!':                'RAR Archive',
            b'\x1f\x8b':            'GZIP',
            b'ID3':                 'MP3 (ID3)',
            b'\xff\xfb':            'MP3 Audio',
            b'\xff\xf3':            'MP3 Audio',
            b'\xff\xf2':            'MP3 Audio',
            b'RIFF':                'WAV/AVI (RIFF)',
            b'OggS':                'OGG',
            b'fLaC':                'FLAC',
            b'\x00\x00\x01\x00':    'ICO',
            b'\xca\xfe\xba\xbe':    'Java/Mach-O',
            b'SQLite':              'SQLite DB',
            b'\xd0\xcf\x11\xe0':    'MS Office (OLE)',
            b'\x50\x4b\x03\x04':    'ZIP Archive',
            b'7z\xbc\xaf':          '7-Zip',
            b'\x42\x5a\x68':        'BZip2',
            b'\xfd7zXZ':            'XZ Archive',
            b'\x00\x61\x73\x6d':    'WebAssembly',
            b'\x1a\x45\xdf\xa3':    'MKV/WebM',
            b'\x00\x00\x00':        'MP4/MOV',
        }

        for sig, name in magic_signatures.items():
            if header.startswith(sig):
                file_type = name
                break

        try:
            with open(file_path, 'rb') as f:
                quick_hash = hashlib.md5(f.read(4096)).hexdigest()[:16]
        except Exception:
            quick_hash = 'N/A'

        # ASCII preview
        ascii_preview = ''.join(
            chr(b) if 32 <= b < 127 else '·' for b in header[:32]
        )

        return {
            'name': p.name,
            'ext': p.suffix,
            'size': size,
            'size_str': SonifyEngine._format_size(size),
            'type': file_type,
            'hash': quick_hash,
            'header_hex': header[:24].hex(' ') if header else 'empty',
            'header_ascii': ascii_preview,
        }

    @staticmethod
    def predict_duration(file_size, frame_rate=44100, channels=1, sample_width=2,
                         offset=0):
        """Предсказать длительность"""
        data_size = max(0, file_size - offset)
        bps = frame_rate * channels * sample_width
        return data_size / bps if bps > 0 else 0

    @staticmethod
    def export(audio, output_path, fmt='wav', bitrate='192k', tags=None):
        """Экспорт — wav всегда работает, остальное зависит от ffmpeg"""
        try:
            params = {'format': fmt}
            if fmt == 'mp3':
                params['bitrate'] = bitrate
            if tags:
                params['tags'] = tags
            audio.export(output_path, **params)
            return output_path
        except Exception as e:
            # Фоллбэк на wav
            if fmt != 'wav':
                wav_path = str(Path(output_path).with_suffix('.wav'))
                audio.export(wav_path, format='wav')
                return wav_path
            raise e

    @staticmethod
    def analyze_waveform(audio, num_points=400):
        """Форма волны для визуализации"""
        try:
            samples = audio.get_array_of_samples()
            if not samples:
                return [0.0] * num_points

            chunk_size = max(1, len(samples) // num_points)
            waveform = []
            max_val = max(abs(min(samples)), abs(max(samples)), 1)

            for i in range(0, len(samples), chunk_size):
                chunk = samples[i:i + chunk_size]
                if chunk:
                    peak = max(abs(min(chunk)), abs(max(chunk)))
                    waveform.append(peak / max_val)

            while len(waveform) < num_points:
                waveform.append(0.0)
            return waveform[:num_points]
        except Exception:
            return [0.0] * num_points

    @staticmethod
    def _format_size(size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


# ══════════════════════════════════════════════════════════════
#  BATCH PROCESSOR
# ══════════════════════════════════════════════════════════════

class BatchSonifier:
    def __init__(self, engine):
        self.engine = engine
        self.is_running = False

    def process_files(self, file_paths, params, effects, output_format,
                      bitrate, output_dir, callback=None):
        self.is_running = True
        results = []
        os.makedirs(output_dir, exist_ok=True)

        for i, fp in enumerate(file_paths):
            if not self.is_running:
                break
            result = self._process_one(fp, params, effects, output_format,
                                       bitrate, output_dir)
            results.append(result)
            if callback:
                callback(i + 1, len(file_paths), result)

        self.is_running = False
        return results

    def _process_one(self, fp, params, effects, fmt, bitrate, output_dir):
        try:
            audio = self.engine.sonify_with_effects(fp, params, effects)

            stem = Path(fp).stem[:50]  # Ограничиваем длину имени
            ext_tag = Path(fp).suffix.strip('.') or 'bin'
            out_name = f"{stem}_{ext_tag}_raw.{fmt}"
            out_path = os.path.join(output_dir, out_name)

            counter = 1
            while os.path.exists(out_path):
                out_name = f"{stem}_{ext_tag}_raw_{counter}.{fmt}"
                out_path = os.path.join(output_dir, out_name)
                counter += 1

            actual_path = self.engine.export(audio, out_path, fmt, bitrate)
            info = self.engine.get_audio_info(audio)
            return {'status': 'ok', 'input': fp, 'output': actual_path, 'info': info}

        except Exception as e:
            return {'status': 'error', 'input': fp, 'error': str(e)}

    def stop(self):
        self.is_running = False


# ══════════════════════════════════════════════════════════════
#  GUI — Full Dark Theme, Only GUI
# ══════════════════════════════════════════════════════════════

class DataBenderApp:
    """Data Bender — любой файл → сырой звук из его байтов"""

    C = {
        'bg':           '#080b10',
        'bg2':          '#0e1218',
        'panel':        '#141a24',
        'panel2':       '#1a2233',
        'input':        '#0a0f16',
        'accent':       '#ff5722',
        'accent_h':     '#ff7043',
        'cyan':         '#00e5ff',
        'green':        '#00e676',
        'red':          '#ff1744',
        'yellow':       '#ffea00',
        'purple':       '#d500f9',
        'orange':       '#ff9100',
        'text':         '#e0e0e0',
        'text2':        '#78849e',
        'border':       '#1e2a3a',
        'border2':      '#2a3a4e',
        'wave_bg':      '#060a10',
        'wave1':        '#00e5ff',
        'wave2':        '#ff5722',
        'wave3':        '#ff1744',
        'sel':          '#1a3a5e',
    }

    def __init__(self):
        self.engine = SonifyEngine()
        self.batch = BatchSonifier(self.engine)
        self.current_audio = None
        self.current_file = None
        self.is_playing = False
        self.temp_dir = tempfile.mkdtemp(prefix='databend_')

        self._build_window()
        self._build_ui()

    def _build_window(self):
        self.root = tk.Tk()
        self.root.title("DATA BENDER — Raw File Sonification")
        self.root.geometry("1100x850")
        self.root.minsize(900, 700)
        self.root.configure(bg=self.C['bg'])

        # Иконка через bitmap если возможно
        try:
            self.root.iconname("DataBender")
        except Exception:
            pass

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self._setup_styles()

    def _setup_styles(self):
        c = self.C

        # Frames
        self.style.configure('Main.TFrame', background=c['bg'])
        self.style.configure('Panel.TFrame', background=c['panel'])
        self.style.configure('Panel2.TFrame', background=c['panel2'])
        self.style.configure('Dark.TFrame', background=c['bg2'])

        # Labels
        self.style.configure('Main.TLabel', background=c['bg'],
                             foreground=c['text'], font=('Segoe UI', 10))
        self.style.configure('Panel.TLabel', background=c['panel'],
                             foreground=c['text'], font=('Segoe UI', 10))
        self.style.configure('Title.TLabel', background=c['bg'],
                             foreground=c['accent'], font=('Segoe UI', 18, 'bold'))
        self.style.configure('Sub.TLabel', background=c['bg'],
                             foreground=c['text2'], font=('Segoe UI', 9))
        self.style.configure('Info.TLabel', background=c['panel'],
                             foreground=c['cyan'], font=('Consolas', 9))
        self.style.configure('Warn.TLabel', background=c['panel'],
                             foreground=c['yellow'], font=('Consolas', 10, 'bold'))
        self.style.configure('Hex.TLabel', background=c['panel'],
                             foreground=c['text2'], font=('Consolas', 8))
        self.style.configure('Status.TLabel', background=c['bg2'],
                             foreground=c['text2'], font=('Segoe UI', 9))
        self.style.configure('Dur.TLabel', background=c['panel'],
                             foreground=c['green'], font=('Consolas', 10))

        # Buttons
        self.style.configure('Accent.TButton', background=c['accent'],
                             foreground='white', font=('Segoe UI', 11, 'bold'),
                             borderwidth=0, padding=(20, 10))
        self.style.map('Accent.TButton',
                       background=[('active', c['accent_h']),
                                   ('disabled', c['border'])])

        self.style.configure('Go.TButton', background=c['green'],
                             foreground='#000', font=('Segoe UI', 12, 'bold'),
                             borderwidth=0, padding=(24, 12))
        self.style.map('Go.TButton',
                       background=[('active', '#66ffa6')])

        self.style.configure('Stop.TButton', background=c['red'],
                             foreground='white', font=('Segoe UI', 10, 'bold'),
                             borderwidth=0, padding=(12, 6))
        self.style.map('Stop.TButton',
                       background=[('active', '#ff616f')])

        self.style.configure('Tool.TButton', background=c['panel2'],
                             foreground=c['text'], font=('Segoe UI', 9),
                             borderwidth=1, padding=(12, 6))
        self.style.map('Tool.TButton',
                       background=[('active', c['border2'])])

        self.style.configure('Preset.TButton', background=c['bg2'],
                             foreground=c['purple'], font=('Segoe UI', 8, 'bold'),
                             borderwidth=1, padding=(6, 4))
        self.style.map('Preset.TButton',
                       background=[('active', c['panel2'])])

        self.style.configure('Mini.TButton', background=c['panel'],
                             foreground=c['text2'], font=('Segoe UI', 8),
                             borderwidth=0, padding=(6, 3))

        # Notebook
        self.style.configure('Dark.TNotebook', background=c['bg'],
                             borderwidth=0)
        self.style.configure('Dark.TNotebook.Tab', background=c['bg2'],
                             foreground=c['text2'], padding=(22, 10),
                             font=('Segoe UI', 10, 'bold'))
        self.style.map('Dark.TNotebook.Tab',
                       background=[('selected', c['panel'])],
                       foreground=[('selected', c['accent'])])

        # LabelFrame
        self.style.configure('Dark.TLabelframe', background=c['panel'],
                             foreground=c['cyan'], borderwidth=2,
                             relief='groove')
        self.style.configure('Dark.TLabelframe.Label', background=c['panel'],
                             foreground=c['cyan'],
                             font=('Segoe UI', 10, 'bold'))

        # Combobox
        self.style.configure('Dark.TCombobox',
                             fieldbackground=c['input'],
                             background=c['panel'],
                             foreground=c['text'],
                             selectbackground=c['sel'],
                             font=('Consolas', 10))
        self.style.map('Dark.TCombobox',
                       fieldbackground=[('readonly', c['input'])])

        # Progressbar
        self.style.configure('Accent.Horizontal.TProgressbar',
                             troughcolor=c['input'],
                             background=c['accent'], borderwidth=0,
                             thickness=8)
        self.style.configure('Green.Horizontal.TProgressbar',
                             troughcolor=c['input'],
                             background=c['green'], borderwidth=0,
                             thickness=6)

        # Scale
        self.style.configure('Dark.Horizontal.TScale',
                             background=c['panel'],
                             troughcolor=c['input'],
                             sliderlength=20)

        # Checkbutton
        self.style.configure('Dark.TCheckbutton', background=c['panel'],
                             foreground=c['text'], font=('Segoe UI', 10))
        self.style.map('Dark.TCheckbutton',
                       background=[('active', c['panel2'])])

        # Entry
        self.style.configure('Dark.TEntry',
                             fieldbackground=c['input'],
                             foreground=c['text'],
                             insertcolor=c['text'])

        # Treeview
        self.style.configure('Dark.Treeview',
                             background=c['panel'],
                             foreground=c['text'],
                             fieldbackground=c['panel'],
                             font=('Consolas', 9),
                             rowheight=24)
        self.style.configure('Dark.Treeview.Heading',
                             background=c['bg2'],
                             foreground=c['accent'],
                             font=('Segoe UI', 10, 'bold'))
        self.style.map('Dark.Treeview',
                       background=[('selected', c['sel'])],
                       foreground=[('selected', c['cyan'])])

        # Separator
        self.style.configure('Dark.TSeparator', background=c['border'])

    def _build_ui(self):
        # Header
        header = ttk.Frame(self.root, style='Main.TFrame')
        header.pack(fill='x', padx=15, pady=(12, 0))

        title_frame = ttk.Frame(header, style='Main.TFrame')
        title_frame.pack(side='left')

        ttk.Label(title_frame, text="DATA BENDER",
                  style='Title.TLabel').pack(side='left')

        ttk.Label(header,
                  text="Any file is raw sound. No conversion. No mercy.",
                  style='Sub.TLabel').pack(side='left', padx=(20, 0), pady=(8, 0))

        # Separator
        sep = tk.Frame(self.root, height=2, bg=self.C['border'])
        sep.pack(fill='x', padx=15, pady=(8, 0))

        # Tabs
        self.notebook = ttk.Notebook(self.root, style='Dark.TNotebook')
        self.notebook.pack(fill='both', expand=True, padx=8, pady=8)

        self._build_sonify_tab()
        self._build_effects_tab()
        self._build_batch_tab()

        # Status bar
        self._build_statusbar()

    # ── TAB 1: SONIFY ─────────────────────────────────────────
    def _build_sonify_tab(self):
        tab = ttk.Frame(self.notebook, style='Main.TFrame')
        self.notebook.add(tab, text='   SONIFY   ')

        # ═══ FILE SECTION ═══
        file_f = ttk.LabelFrame(tab, text="  INPUT FILE  ",
                                style='Dark.TLabelframe')
        file_f.pack(fill='x', padx=12, pady=(12, 6))

        # File path row
        row1 = ttk.Frame(file_f, style='Panel.TFrame')
        row1.pack(fill='x', padx=10, pady=(10, 0))

        self.file_var = tk.StringVar(
            value="Drop any file — EXE, JPG, PDF, ZIP, DLL, MP4, DB, ISO...")
        file_label = ttk.Label(row1, textvariable=self.file_var,
                               style='Panel.TLabel', wraplength=700)
        file_label.pack(side='left', fill='x', expand=True)

        ttk.Button(row1, text="OPEN FILE",
                   style='Accent.TButton',
                   command=self._open_file).pack(side='right', padx=(10, 0))

        # Info row
        info_row = ttk.Frame(file_f, style='Panel.TFrame')
        info_row.pack(fill='x', padx=10, pady=(6, 0))

        self.ftype_var = tk.StringVar(value="")
        ttk.Label(info_row, textvariable=self.ftype_var,
                  style='Warn.TLabel').pack(side='left')

        self.finfo_var = tk.StringVar(value="")
        ttk.Label(info_row, textvariable=self.finfo_var,
                  style='Info.TLabel').pack(side='left', padx=(15, 0))

        # Hex + ASCII
        hex_row = ttk.Frame(file_f, style='Panel.TFrame')
        hex_row.pack(fill='x', padx=10, pady=(4, 8))

        self.hex_var = tk.StringVar(value="")
        ttk.Label(hex_row, textvariable=self.hex_var,
                  style='Hex.TLabel').pack(side='left')

        self.ascii_var = tk.StringVar(value="")
        ttk.Label(hex_row, textvariable=self.ascii_var,
                  style='Hex.TLabel').pack(side='left', padx=(20, 0))

        # ═══ WAVEFORM ═══
        wave_f = ttk.LabelFrame(tab, text="  RAW WAVEFORM  ",
                                style='Dark.TLabelframe')
        wave_f.pack(fill='x', padx=12, pady=6)

        self.wave_canvas = tk.Canvas(wave_f, height=120,
                                     bg=self.C['wave_bg'],
                                     highlightthickness=0,
                                     cursor='crosshair')
        self.wave_canvas.pack(fill='x', padx=8, pady=8)

        # ═══ INTERPRETATION SETTINGS ═══
        settings = ttk.Frame(tab, style='Main.TFrame')
        settings.pack(fill='x', padx=12, pady=6)

        # Left: How to read bytes
        left = ttk.LabelFrame(settings, text="  BYTE INTERPRETATION  ",
                               style='Dark.TLabelframe')
        left.pack(side='left', fill='both', expand=True, padx=(0, 6))

        # Presets grid
        p_label = ttk.Frame(left, style='Panel.TFrame')
        p_label.pack(fill='x', padx=8, pady=(8, 4))
        ttk.Label(p_label,
                  text="PRESETS — same bytes, different sound:",
                  style='Panel.TLabel',
                  font=('Segoe UI', 9, 'bold')).pack(anchor='w')

        p_grid = ttk.Frame(left, style='Panel.TFrame')
        p_grid.pack(fill='x', padx=8, pady=(0, 6))

        presets = list(SonifyEngine.PRESETS.keys())
        cols = 4
        for i, name in enumerate(presets):
            r, cl = divmod(i, cols)
            btn = ttk.Button(p_grid, text=name, style='Preset.TButton',
                             command=lambda n=name: self._apply_preset(n))
            btn.grid(row=r, column=cl, padx=2, pady=2, sticky='ew')
        for cl in range(cols):
            p_grid.columnconfigure(cl, weight=1)

        # Manual controls
        manual = ttk.Frame(left, style='Panel.TFrame')
        manual.pack(fill='x', padx=8, pady=(0, 6))

        # Sample Rate
        self._make_param_row(manual, "Sample Rate:", 'sr_var', '44100',
                             [str(s) for s in SonifyEngine.SAMPLE_RATES])
        # Channels
        self._make_param_row(manual, "Channels:", 'ch_var', '1 (Mono)',
                             ['1 (Mono)', '2 (Stereo)'], readonly=True)
        # Bit Depth
        self._make_param_row(manual, "Bit Depth:", 'bit_var', '16',
                             ['8', '16', '24', '32'], readonly=True)
        # Offset
        off_row = ttk.Frame(manual, style='Panel.TFrame')
        off_row.pack(fill='x', pady=2)
        ttk.Label(off_row, text="Offset (bytes):",
                  style='Panel.TLabel', width=15).pack(side='left')
        self.offset_var = tk.IntVar(value=0)
        off_entry = tk.Entry(off_row, textvariable=self.offset_var, width=12,
                             font=('Consolas', 10), bg=self.C['input'],
                             fg=self.C['text'], insertbackground=self.C['text'],
                             relief='flat', bd=4)
        off_entry.pack(side='right')

        # Duration prediction
        self.predict_var = tk.StringVar(value="")
        ttk.Label(left, textvariable=self.predict_var,
                  style='Dur.TLabel').pack(padx=8, pady=(0, 8))

        # Right: Export
        right = ttk.LabelFrame(settings, text="  EXPORT  ",
                                style='Dark.TLabelframe')
        right.pack(side='right', fill='both', expand=True, padx=(6, 0))

        export_inner = ttk.Frame(right, style='Panel.TFrame')
        export_inner.pack(fill='x', padx=10, pady=8)

        # Format
        self._make_param_row(export_inner, "Format:", 'fmt_var', 'wav',
                             SonifyEngine.EXPORT_FORMATS, readonly=True)
        # Bitrate
        self._make_param_row(export_inner, "Bitrate:", 'br_var', '192k',
                             SonifyEngine.BITRATES, readonly=True)

        # Output dir
        dir_row = ttk.Frame(export_inner, style='Panel.TFrame')
        dir_row.pack(fill='x', pady=4)
        ttk.Label(dir_row, text="Output Dir:",
                  style='Panel.TLabel', width=15).pack(side='left')
        self.out_dir_var = tk.StringVar(value='')
        dir_entry = tk.Entry(dir_row, textvariable=self.out_dir_var, width=18,
                             font=('Consolas', 9), bg=self.C['input'],
                             fg=self.C['text'], insertbackground=self.C['text'],
                             relief='flat', bd=4)
        dir_entry.pack(side='left', fill='x', expand=True, padx=(0, 4))
        ttk.Button(dir_row, text="...", style='Mini.TButton',
                   command=self._choose_output_dir).pack(side='right')

        # Normalize checkbox
        self.normalize_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(right, text="Normalize (changes raw sound!)",
                        variable=self.normalize_var,
                        style='Dark.TCheckbutton').pack(padx=10, pady=4, anchor='w')

        # Note about raw
        ttk.Label(right,
                  text="RAW MODE: bytes are sound as-is.\n"
                       "No processing unless you enable effects.",
                  style='Info.TLabel',
                  font=('Consolas', 8)).pack(padx=10, pady=(4, 8))

        # ═══ ACTION BUTTONS ═══
        actions = ttk.Frame(tab, style='Main.TFrame')
        actions.pack(fill='x', padx=12, pady=8)

        # Player buttons
        player = ttk.Frame(actions, style='Main.TFrame')
        player.pack(side='left')

        ttk.Button(player, text="PREVIEW",
                   style='Tool.TButton',
                   command=self._preview).pack(side='left', padx=3)
        ttk.Button(player, text="STOP",
                   style='Stop.TButton',
                   command=self._stop_preview).pack(side='left', padx=3)
        ttk.Button(player, text="REFRESH",
                   style='Tool.TButton',
                   command=self._refresh_waveform).pack(side='left', padx=3)

        # Export button
        ttk.Button(actions, text="SONIFY & EXPORT",
                   style='Go.TButton',
                   command=self._sonify_export).pack(side='right')

        # Progress
        self.progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(tab, variable=self.progress_var,
                        style='Accent.Horizontal.TProgressbar',
                        maximum=100).pack(fill='x', padx=12, pady=(0, 4))

    def _make_param_row(self, parent, label, var_name, default, values,
                        readonly=False):
        """Helper: создаёт строку параметра с label + combobox"""
        row = ttk.Frame(parent, style='Panel.TFrame')
        row.pack(fill='x', pady=2)
        ttk.Label(row, text=label, style='Panel.TLabel', width=15).pack(side='left')
        var = tk.StringVar(value=default)
        setattr(self, var_name, var)
        state = 'readonly' if readonly else 'normal'
        cb = ttk.Combobox(row, textvariable=var, values=values,
                          style='Dark.TCombobox', state=state, width=12)
        cb.pack(side='right')
        return var

    # ── TAB 2: EFFECTS ────────────────────────────────────────
    def _build_effects_tab(self):
        tab = ttk.Frame(self.notebook, style='Main.TFrame')
        self.notebook.add(tab, text='   EFFECTS   ')

        # Scrollable
        outer = ttk.Frame(tab, style='Main.TFrame')
        outer.pack(fill='both', expand=True)

        canvas = tk.Canvas(outer, bg=self.C['bg'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        scroll_frame = ttk.Frame(canvas, style='Main.TFrame')
        scroll_frame.bind('<Configure>',
                          lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=scroll_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Warning
        warn_f = ttk.Frame(scroll_frame, style='Main.TFrame')
        warn_f.pack(fill='x', padx=12, pady=(12, 6))
        ttk.Label(warn_f,
                  text="Effects modify the raw sound. "
                       "Leave defaults for pure raw byte audio.",
                  style='Sub.TLabel').pack(anchor='w')

        # ── GAIN ──
        gain_f = ttk.LabelFrame(scroll_frame, text="  VOLUME / GAIN  ",
                                style='Dark.TLabelframe')
        gain_f.pack(fill='x', padx=12, pady=6)
        gain_inner = ttk.Frame(gain_f, style='Panel.TFrame')
        gain_inner.pack(fill='x', padx=10, pady=10)

        self.gain_var = tk.DoubleVar(value=0)
        self.gain_label = ttk.Label(gain_inner, text="0.0 dB",
                                    style='Info.TLabel', width=10)
        self.gain_label.pack(side='right')
        ttk.Scale(gain_inner, from_=-40, to=40, variable=self.gain_var,
                  orient='horizontal', style='Dark.Horizontal.TScale',
                  command=lambda v: self.gain_label.config(
                      text=f"{float(v):+.1f} dB")).pack(fill='x', padx=(0, 10))

        # ── FADE ──
        fade_f = ttk.LabelFrame(scroll_frame, text="  FADE IN / OUT  ",
                                style='Dark.TLabelframe')
        fade_f.pack(fill='x', padx=12, pady=6)
        fade_inner = ttk.Frame(fade_f, style='Panel.TFrame')
        fade_inner.pack(fill='x', padx=10, pady=8)

        fi_row = ttk.Frame(fade_inner, style='Panel.TFrame')
        fi_row.pack(fill='x', pady=2)
        ttk.Label(fi_row, text="Fade In (ms):", style='Panel.TLabel',
                  width=18).pack(side='left')
        self.fade_in_var = tk.IntVar(value=0)
        tk.Entry(fi_row, textvariable=self.fade_in_var, width=10,
                 font=('Consolas', 10), bg=self.C['input'],
                 fg=self.C['text'], insertbackground=self.C['text'],
                 relief='flat', bd=4).pack(side='right')

        fo_row = ttk.Frame(fade_inner, style='Panel.TFrame')
        fo_row.pack(fill='x', pady=2)
        ttk.Label(fo_row, text="Fade Out (ms):", style='Panel.TLabel',
                  width=18).pack(side='left')
        self.fade_out_var = tk.IntVar(value=0)
        tk.Entry(fo_row, textvariable=self.fade_out_var, width=10,
                 font=('Consolas', 10), bg=self.C['input'],
                 fg=self.C['text'], insertbackground=self.C['text'],
                 relief='flat', bd=4).pack(side='right')

        # ── SPEED ──
        speed_f = ttk.LabelFrame(scroll_frame, text="  SPEED  ",
                                 style='Dark.TLabelframe')
        speed_f.pack(fill='x', padx=12, pady=6)
        speed_inner = ttk.Frame(speed_f, style='Panel.TFrame')
        speed_inner.pack(fill='x', padx=10, pady=10)

        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_label = ttk.Label(speed_inner, text="1.00x",
                                     style='Info.TLabel', width=10)
        self.speed_label.pack(side='right')
        ttk.Scale(speed_inner, from_=0.05, to=10.0, variable=self.speed_var,
                  orient='horizontal', style='Dark.Horizontal.TScale',
                  command=lambda v: self.speed_label.config(
                      text=f"{float(v):.2f}x")).pack(fill='x', padx=(0, 10))

        # ── MISC ──
        misc_f = ttk.LabelFrame(scroll_frame, text="  MISC  ",
                                style='Dark.TLabelframe')
        misc_f.pack(fill='x', padx=12, pady=6)
        misc_inner = ttk.Frame(misc_f, style='Panel.TFrame')
        misc_inner.pack(fill='x', padx=10, pady=8)

        self.reverse_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(misc_inner, text="Reverse",
                        variable=self.reverse_var,
                        style='Dark.TCheckbutton').pack(anchor='w', pady=2)

        rep_row = ttk.Frame(misc_inner, style='Panel.TFrame')
        rep_row.pack(fill='x', pady=2)
        ttk.Label(rep_row, text="Repeat:", style='Panel.TLabel',
                  width=18).pack(side='left')
        self.repeat_var = tk.IntVar(value=1)
        tk.Entry(rep_row, textvariable=self.repeat_var, width=6,
                 font=('Consolas', 10), bg=self.C['input'],
                 fg=self.C['text'], insertbackground=self.C['text'],
                 relief='flat', bd=4).pack(side='right')

        # ── TRIM ──
        trim_f = ttk.LabelFrame(scroll_frame, text="  TRIM (seconds)  ",
                                style='Dark.TLabelframe')
        trim_f.pack(fill='x', padx=12, pady=6)
        trim_inner = ttk.Frame(trim_f, style='Panel.TFrame')
        trim_inner.pack(fill='x', padx=10, pady=8)

        ts_row = ttk.Frame(trim_inner, style='Panel.TFrame')
        ts_row.pack(fill='x', pady=2)
        ttk.Label(ts_row, text="Start (sec):", style='Panel.TLabel',
                  width=18).pack(side='left')
        self.trim_start_var = tk.DoubleVar(value=0)
        tk.Entry(ts_row, textvariable=self.trim_start_var, width=10,
                 font=('Consolas', 10), bg=self.C['input'],
                 fg=self.C['text'], insertbackground=self.C['text'],
                 relief='flat', bd=4).pack(side='right')

        te_row = ttk.Frame(trim_inner, style='Panel.TFrame')
        te_row.pack(fill='x', pady=2)
        ttk.Label(te_row, text="End (sec, 0=all):", style='Panel.TLabel',
                  width=18).pack(side='left')
        self.trim_end_var = tk.DoubleVar(value=0)
        tk.Entry(te_row, textvariable=self.trim_end_var, width=10,
                 font=('Consolas', 10), bg=self.C['input'],
                 fg=self.C['text'], insertbackground=self.C['text'],
                 relief='flat', bd=4).pack(side='right')

        # Reset button
        ttk.Button(scroll_frame, text="RESET ALL EFFECTS",
                   style='Stop.TButton',
                   command=self._reset_effects).pack(pady=12)

    # ── TAB 3: BATCH ──────────────────────────────────────────
    def _build_batch_tab(self):
        tab = ttk.Frame(self.notebook, style='Main.TFrame')
        self.notebook.add(tab, text='   BATCH   ')

        ttk.Label(tab,
                  text="Mass sonification — every file becomes unique raw sound",
                  style='Sub.TLabel').pack(padx=12, pady=(12, 6))

        # Controls
        ctrl = ttk.Frame(tab, style='Main.TFrame')
        ctrl.pack(fill='x', padx=12, pady=6)

        ttk.Button(ctrl, text="ADD FILES",
                   style='Accent.TButton',
                   command=self._batch_add_files).pack(side='left', padx=3)
        ttk.Button(ctrl, text="ADD FOLDER",
                   style='Tool.TButton',
                   command=self._batch_add_folder).pack(side='left', padx=3)
        ttk.Button(ctrl, text="CLEAR",
                   style='Stop.TButton',
                   command=self._batch_clear).pack(side='left', padx=3)

        ttk.Button(ctrl, text="SONIFY ALL",
                   style='Go.TButton',
                   command=self._batch_start).pack(side='right', padx=3)
        ttk.Button(ctrl, text="STOP",
                   style='Stop.TButton',
                   command=self._batch_stop).pack(side='right', padx=3)

        # Treeview
        tree_frame = ttk.Frame(tab, style='Main.TFrame')
        tree_frame.pack(fill='both', expand=True, padx=12, pady=6)

        columns = ('file', 'type', 'size', 'status')
        self.batch_tree = ttk.Treeview(tree_frame, columns=columns,
                                       show='headings', height=18,
                                       style='Dark.Treeview')

        self.batch_tree.heading('file', text='File')
        self.batch_tree.heading('type', text='Type')
        self.batch_tree.heading('size', text='Size')
        self.batch_tree.heading('status', text='Status')

        self.batch_tree.column('file', width=380)
        self.batch_tree.column('type', width=140, anchor='center')
        self.batch_tree.column('size', width=100, anchor='center')
        self.batch_tree.column('status', width=200, anchor='center')

        tree_scroll = ttk.Scrollbar(tree_frame, orient='vertical',
                                    command=self.batch_tree.yview)
        self.batch_tree.configure(yscrollcommand=tree_scroll.set)
        self.batch_tree.pack(side='left', fill='both', expand=True)
        tree_scroll.pack(side='right', fill='y')

        # Progress
        self.batch_progress = tk.DoubleVar(value=0)
        ttk.Progressbar(tab, variable=self.batch_progress,
                        style='Green.Horizontal.TProgressbar',
                        maximum=100).pack(fill='x', padx=12, pady=6)

        self.batch_status = tk.StringVar(value="Add files to sonify")
        ttk.Label(tab, textvariable=self.batch_status,
                  style='Status.TLabel').pack(fill='x', padx=12)

    # ── STATUSBAR ─────────────────────────────────────────────
    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=self.C['bg2'], height=30)
        bar.pack(fill='x', side='bottom')
        bar.pack_propagate(False)

        self.status_var = tk.StringVar(value="Ready — open any file")
        ttk.Label(bar, textvariable=self.status_var,
                  style='Status.TLabel').pack(side='left', padx=12, pady=4)

        pygame_status = "AUDIO: ON" if HAS_PYGAME else "AUDIO: OFF (pip install pygame)"
        color = self.C['green'] if HAS_PYGAME else self.C['red']
        tk.Label(bar, text=pygame_status, bg=self.C['bg2'],
                 fg=color, font=('Consolas', 8)).pack(side='right', padx=12)

    # ══════════════════════════════════════════════════════════
    #  LOGIC — всё в try/except, работает с любым файлом
    # ══════════════════════════════════════════════════════════

    def _get_params(self):
        try:
            ch_str = self.ch_var.get()
            channels = 2 if '2' in ch_str else 1
            return {
                'frame_rate': int(self.sr_var.get()),
                'channels': channels,
                'sample_width': int(self.bit_var.get()) // 8,
                'offset': max(0, self.offset_var.get()),
            }
        except Exception:
            return {'frame_rate': 44100, 'channels': 1,
                    'sample_width': 2, 'offset': 0}

    def _get_effects(self):
        try:
            return {
                'normalize': self.normalize_var.get(),
                'gain_db': self.gain_var.get(),
                'fade_in_ms': max(0, self.fade_in_var.get()),
                'fade_out_ms': max(0, self.fade_out_var.get()),
                'speed': self.speed_var.get(),
                'reverse': self.reverse_var.get(),
                'repeat': max(1, self.repeat_var.get()),
                'trim_start_sec': max(0, self.trim_start_var.get()),
                'trim_end_sec': max(0, self.trim_end_var.get()),
            }
        except Exception:
            return {}

    def _open_file(self):
        try:
            fp = filedialog.askopenfilename(
                title="Open ANY file — it becomes raw sound",
                filetypes=[("All Files", "*.*"),
                           ("Executables", "*.exe *.dll *.sys"),
                           ("Images", "*.jpg *.png *.bmp *.gif *.ico"),
                           ("Documents", "*.pdf *.doc *.docx *.xls"),
                           ("Archives", "*.zip *.rar *.7z *.tar *.gz"),
                           ("Databases", "*.db *.sqlite *.mdb"),
                           ("Media", "*.mp4 *.avi *.mkv *.mp3 *.wav")]
            )
            if not fp:
                return

            self.current_file = fp
            self.file_var.set(fp)

            # File info
            finfo = self.engine.get_file_info(fp)
            self.ftype_var.set(f"{finfo['type']}")
            self.finfo_var.set(
                f"{finfo['size_str']}  |  {finfo['ext'] or 'no ext'}  |  "
                f"md5: {finfo['hash']}")
            self.hex_var.set(f"HEX: {finfo['header_hex']}")
            self.ascii_var.set(f"ASCII: {finfo['header_ascii']}")

            self._update_prediction()
            self._refresh_waveform()

            self.status_var.set(
                f"Loaded: {finfo['name']} ({finfo['type']}) — "
                f"{finfo['size_str']}")

        except Exception as e:
            self.status_var.set(f"Error opening file: {e}")

    def _update_prediction(self):
        if not self.current_file:
            return
        try:
            params = self._get_params()
            size = os.path.getsize(self.current_file)
            dur = self.engine.predict_duration(
                size, params['frame_rate'], params['channels'],
                params['sample_width'], params['offset'])
            mins = int(dur // 60)
            secs = dur % 60
            self.predict_var.set(
                f"Expected duration: {mins:02d}:{secs:05.2f} ({dur:.1f}s)")
        except Exception:
            self.predict_var.set("")

    def _apply_preset(self, name):
        if name not in SonifyEngine.PRESETS:
            return
        p = SonifyEngine.PRESETS[name]

        self.sr_var.set(str(p['frame_rate']))
        ch = '2 (Stereo)' if p['channels'] == 2 else '1 (Mono)'
        self.ch_var.set(ch)
        self.bit_var.set(str(p['sample_width'] * 8))

        self._update_prediction()
        if self.current_file:
            self._refresh_waveform()

        self.status_var.set(f"Preset: {name}")

    def _refresh_waveform(self):
        if not self.current_file:
            return

        try:
            params = self._get_params()
            audio = self.engine.sonify(
                self.current_file,
                frame_rate=params['frame_rate'],
                channels=params['channels'],
                sample_width=params['sample_width'],
                offset=params['offset'],
            )
            self.current_audio = audio
            self._draw_waveform(audio)
            self._update_prediction()
        except Exception as e:
            self.status_var.set(f"Waveform error: {e}")

    def _draw_waveform(self, audio):
        canvas = self.wave_canvas
        canvas.delete('all')
        canvas.update_idletasks()

        w = canvas.winfo_width()
        h = canvas.winfo_height()

        if w < 20:
            self.root.after(100, lambda: self._draw_waveform(audio))
            return

        num_points = w // 2
        waveform = self.engine.analyze_waveform(audio, num_points=num_points)
        mid = h // 2

        # Grid lines
        for y in range(0, h, 20):
            canvas.create_line(0, y, w, y, fill=self.C['border'], width=1)
        canvas.create_line(0, mid, w, mid, fill=self.C['border2'], width=1)

        # Time markers
        info = self.engine.get_audio_info(audio)
        dur = info['duration_sec']
        if dur > 0:
            for t in range(0, int(dur) + 1, max(1, int(dur / 10))):
                x = int((t / dur) * w) if dur > 0 else 0
                if 0 < x < w:
                    canvas.create_line(x, 0, x, h, fill=self.C['border2'],
                                       width=1, dash=(2, 4))
                    canvas.create_text(x, h - 3, text=f"{t}s",
                                       fill=self.C['text2'], anchor='s',
                                       font=('Consolas', 7))

        # Waveform bars
        bar_w = max(1, w / len(waveform))
        for i, val in enumerate(waveform):
            x = i * bar_w
            bar_h = val * (mid - 4)

            if val > 0.9:
                color = self.C['wave3']
            elif val > 0.55:
                color = self.C['wave2']
            else:
                color = self.C['wave1']

            if bar_h > 0.5:
                canvas.create_rectangle(
                    x, mid - bar_h, x + bar_w - 1, mid + bar_h,
                    fill=color, outline='')

        # Info overlay
        canvas.create_text(8, 8,
                           text=f"{info['duration_str']}  |  "
                                f"{info['dBFS']} dBFS  |  "
                                f"{info['frame_rate']}Hz {info['channels']}ch "
                                f"{info['bits']}bit  |  "
                                f"raw: {self.engine._format_size(info['raw_size'])}",
                           fill=self.C['text2'], anchor='nw',
                           font=('Consolas', 8))

    def _preview(self):
        if not HAS_PYGAME:
            messagebox.showinfo("Info",
                                "Install pygame for audio preview:\npip install pygame")
            return
        if not self.current_file:
            messagebox.showwarning("Warning", "Open a file first!")
            return

        def _do_preview():
            try:
                params = self._get_params()
                effects = self._get_effects()
                audio = self.engine.sonify_with_effects(
                    self.current_file, params, effects)

                temp = os.path.join(self.temp_dir, '_preview.wav')
                audio.export(temp, format='wav')

                pygame.mixer.music.load(temp)
                pygame.mixer.music.play()
                self.is_playing = True
                self.root.after(0,
                                lambda: self.status_var.set("Playing preview..."))
            except Exception as e:
                self.root.after(0,
                                lambda: self.status_var.set(f"Preview error: {e}"))

        threading.Thread(target=_do_preview, daemon=True).start()

    def _stop_preview(self):
        try:
            if HAS_PYGAME and self.is_playing:
                pygame.mixer.music.stop()
                self.is_playing = False
                self.status_var.set("Stopped")
        except Exception:
            pass

    def _sonify_export(self):
        if not self.current_file:
            messagebox.showwarning("Warning", "Open a file first!")
            return

        self.status_var.set("Sonifying...")
        self.progress_var.set(10)
        self.root.update()

        def _do_export():
            try:
                params = self._get_params()
                effects = self._get_effects()

                self.root.after(0, lambda: self.progress_var.set(25))

                audio = self.engine.sonify_with_effects(
                    self.current_file, params, effects)

                self.root.after(0, lambda: self.progress_var.set(65))

                fmt = self.fmt_var.get()
                bitrate = self.br_var.get()
                out_dir = self.out_dir_var.get() or os.path.dirname(
                    self.current_file)
                os.makedirs(out_dir, exist_ok=True)

                src = Path(self.current_file)
                ext_tag = src.suffix.strip('.') or 'bin'
                out_name = f"{src.stem[:60]}_{ext_tag}_raw.{fmt}"
                out_path = os.path.join(out_dir, out_name)

                counter = 1
                while os.path.exists(out_path):
                    out_name = f"{src.stem[:60]}_{ext_tag}_raw_{counter}.{fmt}"
                    out_path = os.path.join(out_dir, out_name)
                    counter += 1

                actual_path = self.engine.export(audio, out_path, fmt, bitrate)

                self.root.after(0, lambda: self.progress_var.set(100))

                info = self.engine.get_audio_info(audio)
                finfo = self.engine.get_file_info(self.current_file)
                actual_name = Path(actual_path).name

                def _show_result():
                    self.status_var.set(
                        f"Exported: {actual_name} ({info['duration_str']})")

                    result = messagebox.askyesnocancel(
                        "Sonified!",
                        f"Input: {finfo['name']}\n"
                        f"Type: {finfo['type']}\n"
                        f"Size: {finfo['size_str']}\n\n"
                        f"Output: {actual_name}\n"
                        f"Duration: {info['duration_str']}\n"
                        f"{info['frame_rate']}Hz {info['channels']}ch "
                        f"{info['bits']}bit\n"
                        f"Level: {info['dBFS']} dBFS\n\n"
                        f"Yes = Open file\n"
                        f"No = Open folder\n"
                        f"Cancel = Close"
                    )

                    if result is True:
                        try:
                            os.startfile(actual_path)
                        except Exception:
                            pass
                    elif result is False:
                        try:
                            os.startfile(os.path.dirname(actual_path))
                        except Exception:
                            pass

                self.root.after(0, _show_result)

            except Exception as e:
                def _show_error():
                    messagebox.showerror("Error", str(e))
                    self.status_var.set(f"Error: {e}")
                self.root.after(0, _show_error)

            finally:
                self.root.after(2500, lambda: self.progress_var.set(0))

        threading.Thread(target=_do_export, daemon=True).start()

    def _choose_output_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.out_dir_var.set(d)

    def _reset_effects(self):
        self.gain_var.set(0)
        self.fade_in_var.set(0)
        self.fade_out_var.set(0)
        self.speed_var.set(1.0)
        self.reverse_var.set(False)
        self.repeat_var.set(1)
        self.trim_start_var.set(0)
        self.trim_end_var.set(0)
        self.normalize_var.set(False)
        self.gain_label.config(text="0.0 dB")
        self.speed_label.config(text="1.00x")
        self.status_var.set("Effects reset — pure raw mode")

    # ── BATCH ─────────────────────────────────────────────────

    def _batch_add_files(self):
        files = filedialog.askopenfilenames(
            title="Select ANY files",
            filetypes=[("All Files", "*.*")]
        )
        if files:
            self._batch_insert(list(files))

    def _batch_add_folder(self):
        d = filedialog.askdirectory(title="Select folder — ALL files become sound")
        if not d:
            return

        files = []
        try:
            for f in Path(d).rglob('*'):
                if f.is_file():
                    files.append(str(f))
        except Exception:
            for f in Path(d).iterdir():
                if f.is_file():
                    files.append(str(f))

        if files:
            self._batch_insert(files)
        else:
            messagebox.showinfo("Info", "No files found")

    def _batch_insert(self, file_paths):
        for fp in file_paths:
            try:
                finfo = self.engine.get_file_info(fp)
                self.batch_tree.insert('', 'end',
                                       values=(finfo['name'], finfo['type'],
                                               finfo['size_str'], 'Pending'),
                                       tags=(fp,))
            except Exception:
                self.batch_tree.insert('', 'end',
                                       values=(Path(fp).name, '?', '?', 'Pending'),
                                       tags=(fp,))

        count = len(self.batch_tree.get_children())
        self.batch_status.set(f"Files: {count}")

    def _batch_clear(self):
        self.batch_tree.delete(*self.batch_tree.get_children())
        self.batch_progress.set(0)
        self.batch_status.set("Cleared")

    def _batch_start(self):
        items = self.batch_tree.get_children()
        if not items:
            messagebox.showwarning("Warning", "Add files first!")
            return

        file_paths = []
        for item in items:
            tags = self.batch_tree.item(item, 'tags')
            if tags:
                file_paths.append(tags[0])

        if not file_paths:
            return

        params = self._get_params()
        effects = self._get_effects()
        fmt = self.fmt_var.get()
        bitrate = self.br_var.get()
        out_dir = self.out_dir_var.get() or os.path.dirname(file_paths[0])

        def _run():
            def callback(current, total, result):
                progress = (current / total) * 100
                self.root.after(0, lambda: self.batch_progress.set(progress))

                item_id = items[current - 1]
                if result['status'] == 'ok':
                    dur = result['info']['duration_str']
                    status = f"OK {dur}"
                else:
                    status = f"ERR: {result['error'][:30]}"

                self.root.after(0, lambda s=status, iid=item_id:
                                self.batch_tree.set(iid, 'status', s))
                self.root.after(0, lambda c=current, t=total:
                                self.batch_status.set(f"Processing {c}/{t}"))

            results = self.batch.process_files(
                file_paths, params, effects, fmt, bitrate, out_dir, callback)

            ok = sum(1 for r in results if r['status'] == 'ok')
            err = sum(1 for r in results if r['status'] == 'error')

            def _done():
                self.batch_status.set(f"Done: {ok} OK, {err} errors")
                messagebox.showinfo(
                    "Batch Complete",
                    f"OK: {ok}\nErrors: {err}\nOutput: {out_dir}")

            self.root.after(0, _done)

        threading.Thread(target=_run, daemon=True).start()

    def _batch_stop(self):
        self.batch.stop()
        self.batch_status.set("Stopped")

    # ── RUN ───────────────────────────────────────────────────
    def run(self):
        self.root.mainloop()

        # Cleanup temp
        try:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT — GUI ONLY
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = DataBenderApp()
    app.run()