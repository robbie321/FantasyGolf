import stripe
from flask import current_app

def _create_transfer(amount_in_cents, destination_account, description):
    """Helper function to create a single Stripe transfer."""
     # Stripe's minimum transfer amount is 1 cent. Do not attempt transfers for 0.
    if amount_in_cents < 1:
        print(f"Skipping transfer for {description}: Amount is zero.")
        return None, None # Return success, as there's nothing to do.

    print(f"Attempting to transfer {amount_in_cents} cents to {destination_account} for: {description}")


    try:
        transfer = stripe.Transfer.create(
            amount=amount_in_cents,
            currency="eur",
            destination=destination_account,
            description=description,
        )
        return transfer, None
    except stripe.error.StripeError as e:
        print(f"Stripe Transfer Error: {e}")
        return None, str(e)

def process_league_payouts(league, winner, club_admin):
    """
    Calculates and processes payouts for both the winner and the club admin.
    This is used for private leagues created by clubs.
    """
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']

    # Calculate the total revenue and the 70% share for the club
    total_revenue = league.entry_fee * len(league.entries)
    creator_total_share = total_revenue * 0.70

    # Calculate the winner's prize based on the percentage set by the admin
    winner_prize_amount = creator_total_share * (league.prize_amount / 100.0)

    # The club admin's profit is what's left of their 70% share
    admin_profit_amount = creator_total_share - winner_prize_amount

    # Convert amounts to cents for the Stripe API
    winner_amount_cents = int(winner_prize_amount * 100)
    admin_amount_cents = int(admin_profit_amount * 100)

    # --- Payout to the Winner ---
    winner_transfer, winner_error = _create_transfer(
        winner_amount_cents,
        winner.stripe_account_id,
        f"Winnings for {league.name}"
    )
    if winner_error:
        return None, None, winner_error

    # --- Payout to the Club Admin ---
    admin_transfer, admin_error = _create_transfer(
        admin_amount_cents,
        club_admin.stripe_account_id,
        f"League hosting profit for {league.name}"
    )
    if admin_error:
        # Optionally, you could try to reverse the winner's transfer here
        return None, None, admin_error

    return winner_prize_amount, admin_profit_amount, None

def create_payout(amount_in_cents, destination_stripe_account_id, league_name):
    """
    Creates a Stripe transfer to send winnings to a user's connected account.
    This is used for public leagues where only the winner is paid out.
    """
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']

    try:
        transfer = stripe.Transfer.create(
            amount=amount_in_cents,
            currency="eur",
            destination=destination_stripe_account_id,
            transfer_group=f"League Winnings: {league_name}",
        )
        return transfer, None
    except stripe.error.StripeError as e:
        print(f"Stripe Error: {e}")
        return None, str(e)