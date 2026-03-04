from app import create_app

app = create_app()

with app.app_context():
    from app.models import Setting
    settings = Setting.query.all()
    print("当前设置:")
    for setting in settings:
        print(f"{setting.key}: {setting.value}")
