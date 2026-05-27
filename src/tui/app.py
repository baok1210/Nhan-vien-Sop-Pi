from textual.app import App
from textual.widgets import Header, Footer

from .screens import MainMenuScreen


class PipelineApp(App):
    TITLE = "Shopee Dropship Pipeline"
    CSS = """
    Screen { background: #1a1b26; }
    .title { text-style: bold; color: #7aa2f7; padding: 1; text-align: center; }
    .subtitle { padding: 0 1; color: #a9b1d6; }
    .section-title { padding: 1 0 0 0; color: #c0caf5; text-style: bold; }
    .store-name { padding: 1; color: #c0caf5; }
    .store-card { height: 3; border: solid #3b4261; margin: 0 1; }
    .store-card Button { margin: 0 1; }
    .info { color: #9ece6a; padding: 0 1; }
    .error { color: #f7768e; }
    .suggestion-info { padding: 1 0 0 0; color: #c0caf5; }
    #store-list, #suggestions-list, #menu-buttons { height: auto; min-height: 5; }
    #log { height: 8; border: solid #3b4261; margin: 0 1; }
    #crawl-log { height: 8; border: solid #3b4261; margin: 0 1; }
    #main-content, #detail-content, #form-content, #edit-content, #crawl-content, #discovery-content, #confirm-content {
        padding: 1 2; }
    Button { margin: 1 0; }
    #edit-content Input { margin: 0 1 0 1; }
    #edit-content Label { padding: 0 1; margin-top: 1; }
    Input { margin: 0 1 1 1; }
    Label { padding: 0 1; color: #a9b1d6; }
    """

    def on_mount(self):
        self.push_screen(MainMenuScreen())
