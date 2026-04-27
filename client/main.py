# client.py — ChordFinder Desktop Client (PyQt6)
import sys
import json
import os
import requests
import io
import warnings
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QStackedWidget, QTabWidget, QDialog, QFormLayout, QGroupBox, QSizeGrip,
    QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QPixmap

warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    import qrcode
    from PIL import Image as PILImage
except ImportError:
    print("Ошибка: установите библиотеки qrcode[pil] и Pillow")
    sys.exit(1)

API_URL = "http://127.0.0.1:8000/api"
TOKEN_FILE = "session.json"

class ToastNotification(QLabel):
    """Всплывающее уведомление без кнопок, авто-скрытие, топ-право"""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet("""
            background-color: #252526; color: #ffffff; padding: 16px 28px;
            border-radius: 8px; font-weight: 600; font-size: 16px;
            border: 1px solid #444;
        """)
        self.setFixedHeight(80)
        self.setFixedWidth(400)
        self.hide()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fade_out)
        
    def show_toast(self):
        if self.parent():
            parent_geom = self.parent().geometry()
            self.move(parent_geom.width() - self.width() - 30, 30)
        self.show()
        self.raise_()
        self.timer.start(3000)
        
    def fade_out(self):
        self.timer.stop()
        self.hide()

class ChordFinderClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChordFinder Desktop")
        self.setGeometry(100, 100, 950, 750)
        
        self.token = None
        self.user_id = None
        self.username = None
        self.user_role = None  # ✅ Добавлено: роль пользователя
        self.toast = ToastNotification("", self)
        
        self.load_session()
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(12, 12, 12, 12)

        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)

        self.login_screen = self.create_login_screen()
        self.register_screen = self.create_register_screen()
        self.main_app_screen = self.create_main_app_screen()

        self.stacked_widget.addWidget(self.login_screen)
        self.stacked_widget.addWidget(self.register_screen)
        self.stacked_widget.addWidget(self.main_app_screen)

        if self.token:
            self.check_auth_and_load()
        else:
            self.stacked_widget.setCurrentIndex(0)

        self.setStyleSheet("""
            QMainWindow { background-color: #121212; color: #e0e0e0; }
            QLabel { color: #e0e0e0; }
            QGroupBox { border: 1px solid #333; border-radius: 6px; margin-top: 8px; padding-top: 10px; font-weight: bold; }
            QLineEdit { padding: 9px; border: 1px solid #444; border-radius: 5px; background-color: #1e1e1e; color: white; selection-background-color: #0078d4; }
            QPushButton { padding: 9px 16px; border-radius: 5px; background-color: #0078d4; color: white; border: none; font-weight: 600; }
            QPushButton:hover { background-color: #005a9e; }
            QPushButton:disabled { background-color: #333; color: #777; }
            QListWidget { background-color: #1a1a1a; border: 1px solid #333; color: #ccc; outline: none; border-radius: 4px; }
            QListWidget::item:selected { background-color: #0078d4; color: white; }
            QTabWidget::pane { border: 1px solid #333; border-radius: 4px; }
            QTabBar::tab { background-color: #1e1e1e; color: #aaa; padding: 9px 15px; border: 1px solid #333; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background-color: #252525; color: white; border-top: 2px solid #0078d4; }
            /* Стиль для кнопки удаления в админке */
            .btn-delete { background-color: #c0392b; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-weight: 500; }
            .btn-delete:hover { background-color: #a93226; }
        """)

    # ========================================================================
    # СЕССИЯ И СЕТЬ
    # ========================================================================
    def load_session(self):
        try:
            with open(TOKEN_FILE, 'r') as f:
                data = json.load(f)
                self.token = data.get('access_token')
                self.user_id = data.get('user_id')
                self.username = data.get('username', 'User')
                self.user_role = data.get('role', 'user')  # ✅ Загружаем роль
        except FileNotFoundError:
            pass

    def save_session(self, token, user_id, username="User", role="user"):
        self.token = token
        self.user_id = user_id
        self.username = username
        self.user_role = role  # ✅ Сохраняем роль
        with open(TOKEN_FILE, 'w') as f:
            json.dump({'access_token': token, 'user_id': user_id, 'username': username, 'role': role}, f)

    def logout(self):
        self.token = self.user_id = self.username = self.user_role = None
        try: os.remove(TOKEN_FILE)
        except OSError: pass
        self.login_username.clear(); self.login_password.clear()
        self.search_input.clear(); self.song_list.clear(); self.fav_list.clear()
        if hasattr(self, 'all_songs_list'): self.all_songs_list.clear()
        if hasattr(self, 'admin_songs_list'): self.admin_songs_list.clear()
        self.stacked_widget.setCurrentIndex(0)

    def check_auth_and_load(self):
        user_data = self.api_request("GET", "/users/me", auth=True, show_error=False)
        if user_data:
            self.save_session(self.token, user_data['id'], user_data['username'], user_data.get('role', 'user'))
            self.show_main_app()
        else:
            self.logout()
            if not self.is_server_online():
                self.toast.setText("Сервер недоступен. Запустите backend.")
                self.toast.show_toast()

    def is_server_online(self):
        try:
            requests.get(f"{API_URL}/../", timeout=1)
            return True
        except: return False

    def api_request(self, method, endpoint, data=None, auth=True, show_error=True):
        headers = {"Content-Type": "application/json"}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        url = f"{API_URL}{endpoint}"
        QApplication.processEvents()
        try:
            if method == "GET": resp = requests.get(url, headers=headers, timeout=10)
            elif method == "POST": resp = requests.post(url, headers=headers, json=data, timeout=10)
            elif method == "DELETE": resp = requests.delete(url, headers=headers, timeout=10)
            
            if resp.status_code == 401:
                if show_error:
                    self.toast.setText("Неверный пароль.")
                    self.toast.show_toast()
                self.logout()
                return None
            
            if resp.status_code in [200, 201]: return resp.json()
            
            err = "Ошибка сервера"
            try: err = resp.json().get('detail', resp.text)
            except: err = resp.text
            if show_error: self.toast.setText(err); self.toast.show_toast()
            return None
        except requests.exceptions.ConnectionError:
            if show_error: self.toast.setText("Нет соединения с сервером"); self.toast.show_toast()
            return None
        except Exception as e:
            if show_error: self.toast.setText(str(e)); self.toast.show_toast()
            return None

    # ========================================================================
    # ЭКРАНЫ
    # ========================================================================
    def create_login_screen(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.setSpacing(15)
        t = QLabel("ChordFinder"); t.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold)); t.setAlignment(Qt.AlignmentFlag.AlignCenter); t.setStyleSheet("color: #0078d4;"); lay.addWidget(t)
        g = QGroupBox("Вход"); fl = QFormLayout(g); fl.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.login_username = QLineEdit(); self.login_username.setPlaceholderText("Логин")
        self.login_password = QLineEdit(); self.login_password.setPlaceholderText("Пароль"); self.login_password.setEchoMode(QLineEdit.EchoMode.Password)
        fl.addRow("Логин:", self.login_username); fl.addRow("Пароль:", self.login_password); lay.addWidget(g)
        b = QPushButton("Войти"); b.setMinimumHeight(42); b.clicked.connect(self.handle_login); lay.addWidget(b)
        l = QLabel("Нет аккаунта? <a href='#' style='color:#0078d4'>Зарегистрироваться</a>")
        l.setOpenExternalLinks(False); l.linkActivated.connect(lambda: self.stacked_widget.setCurrentIndex(1)); l.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.addWidget(l)
        return w

    def handle_login(self):
        u, p = self.login_username.text().strip(), self.login_password.text().strip()
        if not u or not p: self.toast.setText("Заполните все поля"); self.toast.show_toast(); return
        res = self.api_request("POST", "/auth/login", {"username": u, "password": p}, auth=False)
        if res:
            if res.get("requires_2fa"):
                self.temp_token = res.get("temp_token")
                self.handle_2fa_login(u, p, self.temp_token)
            else:
                self.token = res.get("access_token")
                self.check_auth_and_load()
                self.toast.setText("Успешный вход"); self.toast.show_toast()

    def create_register_screen(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.setSpacing(15)
        t = QLabel("Регистрация"); t.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold)); lay.addWidget(t)
        g = QGroupBox("Создание аккаунта"); fl = QFormLayout(g); fl.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.reg_username = QLineEdit(); self.reg_email = QLineEdit(); self.reg_password = QLineEdit(); self.reg_password.setEchoMode(QLineEdit.EchoMode.Password)
        fl.addRow("Логин:", self.reg_username); fl.addRow("Email:", self.reg_email); fl.addRow("Пароль:", self.reg_password); lay.addWidget(g)
        b = QPushButton("Зарегистрироваться"); b.setMinimumHeight(42); b.clicked.connect(self.handle_register); lay.addWidget(b)
        b2 = QPushButton("Назад ко входу"); b2.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0)); lay.addWidget(b2)
        return w

    def handle_register(self):
        u, e, p = self.reg_username.text().strip(), self.reg_email.text().strip(), self.reg_password.text().strip()
        if len(p) < 8: self.toast.setText("Пароль должен содержать минимум 8 символов"); self.toast.show_toast(); return
        if self.api_request("POST", "/auth/register", {"username": u, "email": e, "password": p}, auth=False):
            self.toast.setText("Аккаунт создан. Войдите в систему.")
            self.toast.show_toast()
            self.stacked_widget.setCurrentIndex(0); self.reg_username.clear(); self.reg_email.clear(); self.reg_password.clear()

    def create_main_app_screen(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setSpacing(10)
        top = QHBoxLayout(); self.lbl_user = QLabel("Гость"); self.lbl_user.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        b1 = QPushButton("Выйти"); b1.setFixedWidth(90); b1.clicked.connect(self.logout)
        b2 = QPushButton("Настройка 2FA"); b2.setFixedWidth(150); b2.clicked.connect(self.setup_2fa)
        top.addWidget(self.lbl_user); top.addStretch(); top.addWidget(b2); top.addWidget(b1); lay.addLayout(top)
        tabs = QTabWidget()
        
        # --- Вкладка ПОИСК ---
        search_tab = QWidget(); sl = QVBoxLayout(search_tab)
        si = QHBoxLayout(); self.search_input = QLineEdit(); self.search_input.setPlaceholderText("Поиск: Artist - Title..."); self.search_input.returnPressed.connect(self.perform_search)
        bs = QPushButton("Найти"); bs.setFixedWidth(90); bs.clicked.connect(self.perform_search)
        si.addWidget(self.search_input); si.addWidget(bs); sl.addLayout(si)
        self.song_list = QListWidget(); self.song_list.itemDoubleClicked.connect(self.show_song_details); sl.addWidget(self.song_list)
        
        # --- Вкладка ИЗБРАННОЕ ---
        fav_tab = QWidget(); fl = QVBoxLayout(fav_tab)
        bf = QPushButton("Обновить"); bf.setFixedWidth(120); bf.clicked.connect(self.load_favorites)
        fl.addWidget(bf, alignment=Qt.AlignmentFlag.AlignLeft)
        self.fav_list = QListWidget(); self.fav_list.itemDoubleClicked.connect(self.show_song_details); fl.addWidget(self.fav_list)
        
        # --- Вкладка ВСЕ ПЕСНИ ---
        all_tab = QWidget(); al = QVBoxLayout(all_tab)
        self.all_songs_list = QListWidget()
        self.all_songs_list.itemDoubleClicked.connect(self.show_song_details)
        al.addWidget(self.all_songs_list)
        
        page_layout = QHBoxLayout()
        self.btn_prev_page = QPushButton("← Назад"); self.btn_prev_page.setFixedWidth(100)
        self.btn_prev_page.clicked.connect(lambda: self.load_all_songs(max(0, self.current_page - 1)))
        self.lbl_page = QLabel("Страница 1"); self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter); self.lbl_page.setFixedWidth(120)
        self.btn_refresh = QPushButton("↻ Обновить"); self.btn_refresh.setFixedWidth(110)
        self.btn_refresh.clicked.connect(lambda: self.load_all_songs(self.current_page))
        self.btn_next_page = QPushButton("Вперёд →"); self.btn_next_page.setFixedWidth(100)
        self.btn_next_page.clicked.connect(lambda: self.load_all_songs(self.current_page + 1))
        page_layout.addWidget(self.btn_prev_page); page_layout.addWidget(self.lbl_page)
        page_layout.addWidget(self.btn_refresh); page_layout.addWidget(self.btn_next_page)
        al.addLayout(page_layout)
        self.current_page = 0; self.songs_per_page = 20
        
        # ✅ НОВАЯ ВКЛАДКА: АДМИН (только для админов)
        admin_tab = QWidget(); admin_lay = QVBoxLayout(admin_tab)
        
        # Заголовок
        admin_title = QLabel("🔐 Панель администратора")
        admin_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        admin_title.setStyleSheet("color: #e74c3c; padding: 10px;")
        admin_lay.addWidget(admin_title)
        
        # Список песен с кнопками удаления
        self.admin_songs_list = QListWidget()
        self.admin_songs_list.setStyleSheet("QListWidget { background-color: #1a1a1a; border: 1px solid #333; color: #ccc; }")
        admin_lay.addWidget(self.admin_songs_list)
        
        # Панель управления
        admin_controls = QHBoxLayout()
        btn_refresh_admin = QPushButton("↻ Обновить список")
        btn_refresh_admin.setFixedWidth(150)
        btn_refresh_admin.clicked.connect(self.load_admin_songs)
        admin_controls.addWidget(btn_refresh_admin)
        admin_controls.addStretch()
        admin_lay.addLayout(admin_controls)
        
        # Добавляем вкладку (пока скрыта, покажем после проверки роли)
        self.admin_tab_index = tabs.addTab(admin_tab, "🔐 Админ")
        tabs.setTabVisible(self.admin_tab_index, False)  # Скрыта по умолчанию
        
        tabs.addTab(search_tab, "Поиск"); tabs.addTab(fav_tab, "Избранное"); tabs.addTab(all_tab, "Все песни")
        lay.addWidget(tabs)
        
        # ✅ Показываем админ-вкладку, если пользователь — админ
        if self.user_role == "admin":
            tabs.setTabVisible(self.admin_tab_index, True)
            self.load_admin_songs()  # Загружаем список при старте
        
        return w

    def load_admin_songs(self):
        """Загружает список всех песен для админ-панели"""
        self.admin_songs_list.clear()
        self.admin_songs_list.addItem("Загрузка...")
        QApplication.processEvents()
        
        # Загружаем все песни (без пагинации для админа, или с большой лимитой)
        res = self.api_request("GET", "/admin/users")  # ✅ Или /songs если есть такой эндпоинт
        # Если эндпоинт /admin/users возвращает пользователей, а не песни — используйте /songs
        # Исправленный запрос:
        res = self.api_request("GET", "/songs?limit=200")  # Загружаем до 200 песен
        
        self.admin_songs_list.clear()
        if res is not None:
            if not res:
                self.admin_songs_list.addItem("Список пуст")
            else:
                for s in res:
                    # Создаём виджет строки с песней и кнопкой удаления
                    item_widget = QWidget()
                    item_layout = QHBoxLayout(item_widget)
                    item_layout.setContentsMargins(5, 5, 5, 5)
                    
                    # Текст песни
                    song_label = QLabel(f"{s['artist']} — {s['title']}")
                    song_label.setStyleSheet("color: #e0e0e0;")
                    item_layout.addWidget(song_label, 1)  # Растягивается
                    
                    # Кнопка удаления
                    del_btn = QPushButton("🗑️")
                    del_btn.setFixedSize(32, 32)
                    del_btn.setStyleSheet("""
                        QPushButton { background-color: #c0392b; color: white; border: none; border-radius: 4px; font-size: 14px; }
                        QPushButton:hover { background-color: #a93226; }
                    """)
                    del_btn.setToolTip("Удалить песню")
                    del_btn.clicked.connect(lambda checked, sid=s['id'], artist=s['artist'], title=s['title']: self.delete_song(sid, artist, title))
                    item_layout.addWidget(del_btn)
                    
                    # Добавляем виджет в список
                    list_item = QListWidgetItem()
                    list_item.setSizeHint(item_widget.sizeHint())
                    self.admin_songs_list.addItem(list_item)
                    self.admin_songs_list.setItemWidget(list_item, item_widget)
        else:
            self.admin_songs_list.addItem("Ошибка загрузки")

    def delete_song(self, song_id: int, artist: str, title: str):
        """Удаляет песню из БД с подтверждением"""
        # Диалог подтверждения
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Подтверждение удаления")
        confirm.setText(f"Удалить песню?\n\n🎤 {artist}\n🎵 {title}")
        confirm.setInformativeText("Это действие нельзя отменить.")
        confirm.setIcon(QMessageBox.Icon.Warning)
        confirm.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirm.setDefaultButton(QMessageBox.StandardButton.No)
        confirm.setStyleSheet("""
            QMessageBox { background-color: #1e1e1e; color: #e0e0e0; }
            QPushButton { background-color: #0078d4; color: white; padding: 8px 16px; border-radius: 4px; }
            QPushButton:hover { background-color: #005a9e; }
        """)
        
        if confirm.exec() == QMessageBox.StandardButton.Yes:
            # Выполняем удаление
            res = self.api_request("DELETE", f"/songs/{song_id}")
            if res:
                self.toast.setText(f"Песня '{title}' удалена")
                self.toast.show_toast()
                self.load_admin_songs()  # Перезагружаем список
                self.load_all_songs(self.current_page)  # Обновляем и вкладку "Все песни"
            else:
                self.toast.setText("Ошибка при удалении")
                self.toast.show_toast()

    def show_main_app(self):
        self.stacked_widget.setCurrentIndex(2)
        self.lbl_user.setText(f"Пользователь: {self.username} (ID: {self.user_id})")
        self.load_favorites()
        self.load_all_songs(0)
        # ✅ Показываем админ-вкладку после загрузки данных пользователя
        if self.user_role == "admin":
            tabs = self.stacked_widget.currentWidget().findChild(QTabWidget)
            if tabs:
                tabs.setTabVisible(self.admin_tab_index, True)
                self.load_admin_songs()

    def load_all_songs(self, page: int):
        """Загружает страницу списка всех песен"""
        self.current_page = page
        skip = page * self.songs_per_page
        self.all_songs_list.clear()
        self.all_songs_list.addItem("Загрузка...")
        QApplication.processEvents()
        res = self.api_request("GET", f"/songs?skip={skip}&limit={self.songs_per_page}")
        self.all_songs_list.clear()
        if res is not None:
            if not res:
                self.all_songs_list.addItem("Список пуст")
                self.btn_prev_page.setEnabled(False)
                self.btn_next_page.setEnabled(False)
            else:
                for s in res:
                    h = s.get('hits', 0)
                    it = QListWidgetItem(f"{s['artist']} — {s['title']} | 👁️ {h:,}" if h > 0 else f"{s['artist']} — {s['title']}")
                    it.setData(Qt.ItemDataRole.UserRole, s['id'])
                    self.all_songs_list.addItem(it)
                self.btn_prev_page.setEnabled(page > 0)
                self.btn_next_page.setEnabled(len(res) == self.songs_per_page)
            self.lbl_page.setText(f"Страница {page + 1}")
        else:
            self.all_songs_list.addItem("Ошибка загрузки")
            self.btn_prev_page.setEnabled(False)
            self.btn_next_page.setEnabled(False)

    def perform_search(self):
        q = self.search_input.text().strip()
        if not q: return
        self.song_list.clear(); self.song_list.addItem("Поиск..."); QApplication.processEvents()
        res = self.api_request("POST", "/search", {"query": q})
        self.song_list.clear()
        if res is not None:
            if not res: self.song_list.addItem("Ничего не найдено")
            else:
                for s in res:
                    h = s.get('hits', 0)
                    it = QListWidgetItem(f"{s['artist']} — {s['title']} | 👁️ {h:,}" if h > 0 else f"{s['artist']} — {s['title']}")
                    it.setData(Qt.ItemDataRole.UserRole, s['id']); self.song_list.addItem(it)
        else: self.song_list.addItem("Ошибка поиска")

    def load_favorites(self):
        self.fav_list.clear(); self.fav_list.addItem("Загрузка..."); QApplication.processEvents()
        res = self.api_request("GET", "/favorites")
        self.fav_list.clear()
        if res is not None:
            if not res: self.fav_list.addItem("Список пуст")
            else:
                for s in res:
                    h = s.get('hits', 0)
                    it = QListWidgetItem(f"{s['artist']} — {s['title']} | 👁️ {h:,}" if h > 0 else f"{s['artist']} — {s['title']}")
                    it.setData(Qt.ItemDataRole.UserRole, s['id']); self.fav_list.addItem(it)
        else: self.fav_list.addItem("Ошибка загрузки")

    # ========================================================================
    # ДЕТАЛИ ПЕСНИ
    # ========================================================================
    def show_song_details(self, item):
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not sid: return
        sd = self.api_request("GET", f"/songs/{sid}")
        if not sd: return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"{sd['artist']} - {sd['title']}")
        dlg.resize(950, 800)
        dlg.setMinimumSize(600, 400)
        dlg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dlg.setStyleSheet("QDialog { background-color: #0d0d0d; border: 1px solid #2a2a2a; }")

        main_lay = QVBoxLayout(dlg)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background-color: #1a1a1a; border-bottom: 1px solid #333;")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(20, 12, 20, 12)
        hlay.setSpacing(15)

        title_lbl = QLabel(f"{sd['artist']} — {sd['title']}")
        title_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #ffffff;")
        hlay.addWidget(title_lbl)

        hits_l = QLabel(f"Просмотры: {sd.get('hits', 0):,}")
        hits_l.setStyleSheet("color: #888; font-size: 13px;")
        hlay.addWidget(hits_l)
        hlay.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(36, 36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { 
                background: #2a2a2a; color: #ffffff; border: 2px solid #555; 
                border-radius: 18px; font-size: 20px; font-weight: bold; 
            }
            QPushButton:hover { background: #c0392b; color: #fff; border-color: #c0392b; }
            QPushButton:pressed { background: #a93226; }
        """)
        close_btn.clicked.connect(dlg.reject)
        hlay.addWidget(close_btn)

        main_lay.addWidget(header)

        dlg._dragging = False; dlg._drag_offset = None
        def on_press(e):
            if e.button() == Qt.MouseButton.LeftButton:
                dlg._dragging = True
                dlg._drag_offset = e.globalPosition().toPoint() - dlg.pos()
                header.setCursor(Qt.CursorShape.ClosedHandCursor)
        def on_move(e):
            if dlg._dragging and (e.buttons() & Qt.MouseButton.LeftButton):
                dlg.move(e.globalPosition().toPoint() - dlg._drag_offset)
        def on_release(e):
            dlg._dragging = False
            header.setCursor(Qt.CursorShape.OpenHandCursor)
        header.mousePressEvent = on_press; header.mouseMoveEvent = on_move; header.mouseReleaseEvent = on_release
        header.setCursor(Qt.CursorShape.OpenHandCursor)

        content = QWidget()
        clayout = QVBoxLayout(content)
        clayout.setContentsMargins(20, 20, 20, 20)
        clayout.setSpacing(15)

        tg = QGroupBox("Текст песни")
        tg.setStyleSheet("QGroupBox { border: 1px solid #333; border-radius: 6px; margin-top: 0; padding-top: 10px; font-weight: bold; color: #fff; }")
        tl = QVBoxLayout(tg)
        
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setStyleSheet("""
            QTextEdit { background-color: #0a0a0a; color: #d4d4d4; border: 1px solid #222; padding: 16px;
                        font-family: 'Consolas', 'Menlo', 'Courier New', monospace; font-size: 14px; line-height: 1.55; }
        """)
        content_text = sd.get('text', '').strip()
        if not content_text:
            chords = sd.get('chords', [])
            content_text = f"[Аккорды: {', '.join(chords[:20])}{'...' if len(chords)>20 else ''}]\n\n(Полный текст не найден)"
        txt.setText(content_text)
        tl.addWidget(txt)
        clayout.addWidget(tg)

        bl = QHBoxLayout()
        b1 = QPushButton("В избранное"); b1.clicked.connect(lambda: self.toggle_favorite(sid, True, dlg))
        b2 = QPushButton("Убрать из избранного"); b2.clicked.connect(lambda: self.toggle_favorite(sid, False, dlg))
        bl.addWidget(b1); bl.addWidget(b2); bl.addStretch()
        clayout.addLayout(bl)
        main_lay.addWidget(content, 1)

        footer = QHBoxLayout(); footer.addStretch()
        size_grip = QSizeGrip(dlg); size_grip.setFixedSize(24, 24)
        size_grip.setStyleSheet("QSizeGrip { background: transparent; }")
        footer.addWidget(size_grip)
        main_lay.addLayout(footer)

        dlg.exec()

    def toggle_favorite(self, sid, add, dlg):
        if add:
            if self.api_request("POST", "/favorites", {"song_id": sid}):
                self.toast.setText("Добавлено в избранное"); self.toast.show_toast()
        else:
            if self.api_request("DELETE", f"/favorites/{sid}"):
                self.toast.setText("Удалено из избранного"); self.toast.show_toast()
                dlg.reject(); self.load_favorites()

    # ========================================================================
    # 2FA
    # ========================================================================
    def setup_2fa(self):
        sd = self.api_request("POST", "/auth/2fa/setup")
        if not sd: return
        sk, qr = sd.get('secret'), sd.get('qr_code_uri')
        if not qr: self.toast.setText("Сервер не вернул QR-код"); self.toast.show_toast(); return

        img = qrcode.make(qr); buf = io.BytesIO(); img.save(buf, "PNG"); buf.seek(0)
        pix = QPixmap(); pix.loadFromData(buf.getvalue())

        dlg = QDialog(self); dlg.setWindowTitle("Настройка 2FA"); dlg.resize(400, 480); dlg.setStyleSheet(self.styleSheet())
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Отсканируйте QR-код в приложении-аутентификаторе:"))
        lq = QLabel(); lq.setPixmap(pix.scaled(220,220,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)); lq.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.addWidget(lq)
        lk = QLabel(f"Секретный ключ: {sk}"); lk.setAlignment(Qt.AlignmentFlag.AlignCenter); lk.setStyleSheet("font-family:monospace; background:#222; padding:6px; border-radius:4px;"); lay.addWidget(lk)
        lay.addWidget(QLabel("Введите 6-значный код подтверждения:"))
        inp = QLineEdit(); inp.setMaxLength(6); inp.setAlignment(Qt.AlignmentFlag.AlignCenter); inp.setFont(QFont("Arial",14,QFont.Weight.Bold)); lay.addWidget(inp)
        bv = QPushButton("Активировать"); bv.clicked.connect(lambda: self.verify_2fa_code(inp.text(), dlg)); lay.addWidget(bv)
        dlg.exec()

    def verify_2fa_code(self, code, dlg):
        if len(code)!=6 or not code.isdigit(): self.toast.setText("Код должен содержать 6 цифр"); self.toast.show_toast(); return
        if self.api_request("POST", "/auth/2fa/verify", {"code": code}):
            self.toast.setText("2FA успешно активирован"); self.toast.show_toast(); dlg.accept()

    def handle_2fa_login(self, username, password, temp_token):
        dlg = QDialog(self); dlg.setWindowTitle("Подтверждение входа (2FA)"); dlg.setModal(True); dlg.resize(380, 220); dlg.setStyleSheet(self.styleSheet())
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"Введите код подтверждения для: {username}"))
        inp = QLineEdit(); inp.setMaxLength(6); inp.setAlignment(Qt.AlignmentFlag.AlignCenter); inp.setFont(QFont("Arial",16,QFont.Weight.Bold)); inp.setPlaceholderText("000000"); lay.addWidget(inp)
        bv = QPushButton("Подтвердить вход"); bv.setMinimumHeight(38); lay.addWidget(bv)
        dlg.show(); inp.setFocus()
        def try_verify():
            code = inp.text()
            if len(code)!=6 or not code.isdigit(): self.toast.setText("Код должен содержать 6 цифр"); self.toast.show_toast(); return
            self.verify_2fa_login_code(code, temp_token, username, dlg)
        bv.clicked.connect(try_verify); inp.returnPressed.connect(try_verify)

    def verify_2fa_login_code(self, code, temp_token, username, dlg):
        headers = {"Content-Type": "application/json", "temp-token": temp_token}
        try:
            r = requests.post(f"{API_URL}/auth/2fa/verify-login", json={"code": code}, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                self.token = data.get("access_token")
                self.check_auth_and_load()
                self.toast.setText("Вход выполнен"); self.toast.show_toast()
                dlg.accept()
            else:
                self.toast.setText("Неверный код 2FA"); self.toast.show_toast()
        except:
            self.toast.setText("Ошибка сети"); self.toast.show_toast()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    w = ChordFinderClient()
    w.show()
    sys.exit(app.exec())