import logging
from django.contrib.auth import get_user_model
from .models import UserCredit, CreditTransaction

logger = logging.getLogger(__name__)

# Credit Cost Table
COST_NORMAL_QA = 10                # Simple text Q&A (no web search or document generation)
COST_ADVANCED_ANALYSIS = 15        # Complex code or financial model analysis
COST_WEB_SEARCH = 25               # Real-time web search tool usage
COST_DOCUMENT_GENERATION = 50      # Heavy work: Python sandbox execution + PowerPoint/Excel/Word/PDF generation
COST_COMBINED_WORK = 70            # Both Web Search and Document Generation executed in one turn


def get_or_create_user_credit(user) -> UserCredit:
    """
    Returns or creates a UserCredit record for the given user.
    """
    user_credit, _ = UserCredit.objects.get_or_create(user=user)
    return user_credit


def claim_trial_credits_for_user(user, claim=None) -> tuple[UserCredit, bool, str]:
    """
    Grants 1000 trial credits to the user.
    Returns (user_credit, was_granted, message).
    """
    user_credit = get_or_create_user_credit(user)

    if user_credit.has_claimed_trial:
        logger.info("User %s already claimed trial credits. Current balance: %d", user, user_credit.credits)
        return user_credit, False, f"Trial credits were already claimed for this account. Current balance: {user_credit.credits} credits."

    # Grant 1000 credits
    user_credit.has_claimed_trial = True
    user_credit.save(update_fields=['has_claimed_trial'])
    user_credit.grant_credits(
        amount=1000,
        action=CreditTransaction.Action.CLAIM_TRIAL,
        description="Welcome bonus: 1000 free trial credits claimed via Claim Trial form.",
    )

    if claim is not None:
        claim.user = user
        claim.credits_granted = 1000
        claim.save(update_fields=['user', 'credits_granted'])

    logger.info("Granted 1000 trial credits to user %s. New balance: %d", user, user_credit.credits)
    return user_credit, True, "1000 trial credits successfully added to your account!"


def calculate_credits_for_ai_work(
    intent: str = 'general',
    web_search_used: bool = False,
    document_generated: bool = False,
    files_count: int = 0,
) -> tuple[int, str, str]:
    """
    Dynamically determines credit cost based on the AI work performed:
    - Normal Q&A: light work -> 10 credits
    - Advanced Code / Financial Analysis: 15 credits
    - Web Search: real-time search queries -> 25 credits
    - Document Generation: code sandbox execution & file creation -> 50 credits
    - Combined (Web Search + Doc Gen): 70 credits

    Returns:
        (cost, user_friendly_reason, action_type)
    """
    if web_search_used and document_generated:
        extra_files_cost = max(0, files_count - 1) * 10
        cost = COST_COMBINED_WORK + extra_files_cost
        file_desc = f" ({files_count} files)" if files_count > 1 else ""
        return (
            cost,
            f"Web Search & Document Generation{file_desc}",
            CreditTransaction.Action.COMBINED_AI_WORK,
        )

    if document_generated:
        extra_files_cost = max(0, files_count - 1) * 10
        cost = COST_DOCUMENT_GENERATION + extra_files_cost
        file_desc = f" ({files_count} files)" if files_count > 1 else ""
        return (
            cost,
            f"Document Generation{file_desc}",
            CreditTransaction.Action.DOCUMENT_GENERATION,
        )

    if web_search_used:
        return (
            COST_WEB_SEARCH,
            "Web Search",
            CreditTransaction.Action.WEB_SEARCH,
        )

    if intent in ("financial_analysis", "code"):
        return (
            COST_ADVANCED_ANALYSIS,
            f"Advanced {intent.replace('_', ' ').title()}",
            CreditTransaction.Action.NORMAL_QA,
        )

    return (
        COST_NORMAL_QA,
        "Normal Question & Answer",
        CreditTransaction.Action.NORMAL_QA,
    )


def deduct_user_credits_for_ai_work(
    user,
    intent: str = 'general',
    web_search_used: bool = False,
    document_generated: bool = False,
    files_count: int = 0,
    chat_id=None,
) -> tuple[int, int, str]:
    """
    Calculates and deducts credits from the user's account for AI work.
    Logs the transaction in CreditTransaction.

    Returns:
        (deducted_amount, remaining_credits, reason)
    """
    if not user:
        return 0, 0, "No user"

    user_credit = get_or_create_user_credit(user)
    cost, reason, action = calculate_credits_for_ai_work(
        intent=intent,
        web_search_used=web_search_used,
        document_generated=document_generated,
        files_count=files_count,
    )

    desc_parts = [reason]
    if chat_id:
        desc_parts.append(f"Chat #{chat_id}")
    description = " — ".join(desc_parts)

    deducted = user_credit.deduct_credits(
        amount=cost,
        action=action,
        description=description,
    )

    logger.info(
        "Deducted %d credits from user %s for %s. Remaining: %d",
        deducted, user, reason, user_credit.credits,
    )
    return deducted, user_credit.credits, reason


def check_user_credit_balance(user, minimum_required: int = 10) -> tuple[bool, int]:
    """
    Checks if user has enough credits to make a request.
    Returns (has_sufficient, current_balance).
    """
    if not user:
        return False, 0
    user_credit = get_or_create_user_credit(user)
    return user_credit.credits >= minimum_required, user_credit.credits
