# Create debug_beat_schedule.py and run it

def debug_beat_schedule():
    print("Debugging Beat Schedule Loading...")
    print("=" * 50)

    try:
        # Test 1: Check if celeryconfig.py is being loaded
        print("1. Testing celeryconfig.py import...")
        try:
            import celeryconfig
            print("✅ celeryconfig.py imports successfully")

            # Check if beat_schedule exists in celeryconfig
            if hasattr(celeryconfig, 'beat_schedule'):
                schedule = celeryconfig.beat_schedule
                print(f"✅ beat_schedule found with {len(schedule)} tasks:")
                for task_name in schedule.keys():
                    print(f"   - {task_name}")
            else:
                print("❌ No beat_schedule found in celeryconfig.py")

        except ImportError as e:
            print(f"❌ Cannot import celeryconfig.py: {e}")
        except Exception as e:
            print(f"❌ Error with celeryconfig.py: {e}")

        print("\n2. Testing Celery app configuration...")
        from fantasy_league_app import celery

        # Check what configuration Celery actually has
        beat_schedule = celery.conf.get('beat_schedule', {})
        print(f"Celery app beat_schedule: {len(beat_schedule)} tasks")

        if beat_schedule:
            for task_name, config in beat_schedule.items():
                print(f"   - {task_name}: {config.get('task')}")
        else:
            print("❌ Celery app has no beat_schedule configured")

        # Check other relevant config
        broker_url = celery.conf.get('broker_url')
        result_backend = celery.conf.get('result_backend')
        print(f"Broker URL: {broker_url}")
        print(f"Result Backend: {result_backend}")

        print("\n3. Testing Flask config integration...")
        from fantasy_league_app import create_app
        app = create_app()

        with app.app_context():
            flask_beat_schedule = app.config.get('beat_schedule', {})
            print(f"Flask config beat_schedule: {len(flask_beat_schedule)} tasks")

        print("\n4. Current working directory and file check...")
        import os
        print(f"Current working directory: {os.getcwd()}")
        print(f"celeryconfig.py exists: {os.path.exists('celeryconfig.py')}")

        if os.path.exists('celeryconfig.py'):
            with open('celeryconfig.py', 'r') as f:
                content = f.read()
                if 'beat_schedule' in content:
                    print("✅ beat_schedule found in celeryconfig.py file")
                else:
                    print("❌ beat_schedule NOT found in celeryconfig.py file")

        return True

    except Exception as e:
        print(f"❌ Error during debugging: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    debug_beat_schedule()