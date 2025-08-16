import stripe
from flask import current_app

def create_express_account(email):
    """Creates a new Stripe Express account for a user."""
    try:
        account = stripe.Account.create(
            type='express',
            email=email,
            capabilities={
                'card_payments': {'requested': True},
                'transfers': {'requested': True},
            },
        )
        return account
    except Exception as e:
        current_app.logger.error(f"Failed to create Stripe account: {e}")
        return None

def create_account_link(account_id, refresh_url, return_url):
    """
    Creates a link for the user to onboard to Stripe.
    This is the correct, direct way to call the Stripe API.
    """
    try:
        account_link = stripe.AccountLink.create(
            account=account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type='account_onboarding',
        )
        return account_link
    except Exception as e:
        current_app.logger.error(f"Failed to create Stripe account link: {e}")
        return None

def _create_transfer(amount_in_cents, destination_account, description):
    """Helper function to create a single Stripe transfer."""
    # Stripe's minimum transfer amount is 1 cent. Do not attempt transfers for 0.
    if amount_in_cents < 1:
        print(f"Skipping transfer for {description}: Amount is zero.")
        return None, None # Return success, as there's nothing to do.

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

def process_payouts(league, winners, club_admin=None):
    """
    Calculates and processes payouts for a list of winners and an optional club admin.
    """
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']

    total_revenue = league.entry_fee * len(league.entries)
    num_winners = len(winners)

    if league.is_public:
        total_prize_pool = total_revenue * (league.prize_amount / 100.0)
    else: # Private league
        creator_total_share = total_revenue * 0.70
        total_prize_pool = creator_total_share * (league.prize_amount / 100.0)
        admin_profit = creator_total_share - total_prize_pool
        admin_profit_cents = int(admin_profit * 100)

        # Pay the club admin their share
        if club_admin and club_admin.stripe_account_id:
            _, admin_error = _create_transfer(
                admin_profit_cents,
                club_admin.stripe_account_id,
                f"League hosting profit for {league.name}"
            )
            if admin_error:
                return None, admin_error

    # Split the prize pool among the winners
    prize_per_winner = total_prize_pool / num_winners
    prize_per_winner_cents = int(prize_per_winner * 100)

    for winner in winners:
        if not winner.stripe_account_id:
            return None, f"Winner {winner.full_name} is missing a Stripe account ID."

        _, winner_error = _create_transfer(
            prize_per_winner_cents,
            winner.stripe_account_id,
            f"Winnings for {league.name} (split)"
        )
        if winner_error:
            return None, winner_error

    return total_prize_pool, None

def create_payout(amount_in_cents, destination_stripe_account_id, league_name):
    """
    Creates a Stripe transfer to send winnings to a user's connected account.
    This is used for public leagues where only the winner is paid out.
    """
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']

    if amount_in_cents < 1:
        print(f"Skipping transfer for {league_name}: Amount is zero.")
        return None, None

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
