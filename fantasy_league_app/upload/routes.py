import os
import csv
from flask import render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from fantasy_league_app import db
from fantasy_league_app.models import Player
from fantasy_league_app.utils import safe_float_odds, safe_int_score, get_player_by_full_name

from . import upload_bp

@upload_bp.route('/', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part in the request', 'danger')
            return redirect(request.url)

        file = request.files['file']

        if file.filename == '':
            flash('No file selected for upload', 'danger')
            return redirect(request.url)

        if file and file.filename.endswith('.csv'):
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], secure_filename('Players_temp_upload.csv'))
            try:
                file.save(filepath)

                with open(filepath, newline='', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    updated_count = 0
                    added_count = 0
                    errors = []

                    for row_num, row in enumerate(reader, start=1):
                        name = row.get('Name')
                        surname = row.get('Surname')
                        odds = safe_float_odds(row.get('Odds', '0'))
                        current_score = safe_int_score(row.get('Current Score', '0'))

                        if not name or not surname:
                            errors.append(f'Row {row_num}: Missing \'Name\' or \'Surname\'. Skipping.')
                            continue

                        player = Player.query.filter_by(name=name, surname=surname).first()

                        if player:
                            player.odds = odds
                            player.current_score = current_score
                            updated_count += 1
                        else:
                            new_player = Player(name=name, surname=surname, odds=odds, current_score=current_score)
                            db.session.add(new_player)
                            added_count += 1

                    db.session.commit()
                    flash(f'Player data uploaded successfully! Added {added_count} new players, updated {updated_count} existing players.', 'success')
                    if errors:
                        flash(f'Warnings during upload: {"; ".join(errors)}', 'warning')

                # Corrected Python file deletion
                if os.path.exists(filepath):
                    os.remove(filepath)
                return redirect(url_for('main.index'))

            except Exception as e:
                db.session.rollback()
                flash(f'Error processing player data: {e}', 'danger')
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Only CSV files are allowed', 'danger')

    return render_template('upload/upload.html')
