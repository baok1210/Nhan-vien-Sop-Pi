import os
from flask import Flask


class AppAdmin:
    def __init__(self, app=None):
        self.app = app
        self._menu_items = []
        if app:
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        self._inject_context()

    def add_view(self, bp, name='', icon='', endpoint=''):
        self.app.register_blueprint(bp)
        self._menu_items.append({
            'name': name,
            'endpoint': endpoint or bp.name + '.index',
            'icon': icon,
        })

    def _inject_context(self):
        @self.app.context_processor
        def inject_admin():
            return {'admin_menu': self._menu_items}
