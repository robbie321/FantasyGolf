# fantasy_league_app/cli.py
import click
from flask import current_app
from fantasy_league_app.extensions import db
from .models import User


def register_cli_commands(app):
    """Register all CLI commands with the app"""

    @app.cli.command()
    @click.option('--user-id', type=int, required=True)
    @click.option('--title', default='Test Notification')
    @click.option('--body', default='This is a test notification')
    def test_push(user_id, title, body):
        """Send a test push notification"""
        from fantasy_league_app.push.services import push_service

        try:
            result = push_service.send_notification_sync(
                user_ids=[user_id],
                notification_type='test',
                title=title,
                body=body
            )
            click.echo(f'Notification sent: {result}')
        except Exception as e:
            click.echo(f'Error: {e}')

    @app.cli.command()
    def push_stats():
        """Show push notification statistics"""
        from fantasy_league_app.push.models import NotificationLog
        from fantasy_league_app.models import PushSubscription

        total_subscriptions = PushSubscription.query.count()
        total_notifications = NotificationLog.query.count()
        successful_notifications = NotificationLog.query.filter_by(status='sent').count()

        click.echo(f'Total subscriptions: {total_subscriptions}')
        click.echo(f'Total notifications sent: {total_notifications}')
        click.echo(f'Successful notifications: {successful_notifications}')

        if total_notifications > 0:
            success_rate = (successful_notifications / total_notifications) * 100
            click.echo(f'Success rate: {success_rate:.1f}%')

    @app.cli.command()
    def init_push_templates():
        """Initialize push notification templates"""
        from fantasy_league_app.push.models import create_notification_templates

        try:
            create_notification_templates()
            click.echo('Push notification templates created successfully!')
        except Exception as e:
            click.echo(f'Error creating templates: {e}')

    @app.cli.command('hello')
    def hello():
        """Simple test command to verify CLI is working"""
        click.echo('🎉 Hello from Fantasy Golf CLI!')
        click.echo('✅ CLI commands are working properly')


    @click.command('trigger-scores')
    def trigger_score_updates():
        """Manually trigger score updates for active tournaments"""
        from fantasy_league_app.tasks import schedule_score_updates_for_the_week
        result = schedule_score_updates_for_the_week.delay()
        click.echo(f"Score update task triggered: {result.id}")


    @app.cli.command('list-users')
    @click.option('--limit', default=5, help='Number of users to show')
    def list_users(limit):
        """List users for testing"""
        try:
            users = User.query.limit(limit).all()
            if not users:
                click.echo('No users found in database')
                return

            click.echo(f'Found {len(users)} users:')
            for user in users:
                click.echo(f'  • ID: {user.id:3d} | {user.full_name} | {user.email}')

        except Exception as e:
            click.echo(f'Error: {str(e)}')


    @app.cli.command('test-push')
    @click.option('--user-id', type=int, required=True, help='User ID to send notification to')
    @click.option('--title', default='Test Notification', help='Notification title')
    @click.option('--body', default='This is a test notification', help='Notification body')
    def test_push(user_id, title, body):
        """Send a test push notification to a user"""
        try:
            # Check if user exists
            user = User.query.get(user_id)
            if not user:
                click.echo(f'❌ User with ID {user_id} not found')
                return

            click.echo(f'📱 Sending notification to {user.full_name} (ID: {user_id})')

            # Check if push system is set up
            try:
                from fantasy_league_app.push.services import push_service
                result = push_service.send_notification_sync(
                    user_ids=[user_id],
                    notification_type='test',
                    title=title,
                    body=body
                )
                click.echo(f'✅ Result: {result}')

            except ImportError:
                click.echo('❌ Push notification system not set up yet')
                click.echo('💡 Make sure you\'ve created the push/ directory and files')

        except Exception as e:
            click.echo(f'❌ Error: {str(e)}')