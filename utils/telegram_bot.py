import logging
from pathlib import Path
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from telegram import constants
import asyncio
import re

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class PimmichBot:
    """
    Encapsulates the Telegram bot logic for Pimmich.
    Handles user authorization, photo reception, and invitation codes.
    """
    def __init__(self, token, authorized_users_str, guest_users, photo_callback, validation_callback):
        self.token = token
        try:
            self.authorized_users = {int(uid.strip()) for uid in authorized_users_str.split(',') if uid.strip().isdigit()}
        except (ValueError, TypeError):
            self.authorized_users = set()
            logger.warning("Could not parse telegram_authorized_users. No admin will be set.")
            
        self.guest_users = {int(uid): name for uid, name in guest_users.items()}
        self.photo_callback = photo_callback
        self.validation_callback = validation_callback
        
        # Build the application
        self.app = Application.builder().token(self.token).build()
        self._register_handlers()

    def _register_handlers(self):
        """Registers all the command and message handlers for the bot."""
        self.app.add_handler(CommandHandler(["start", "help"], self.start_command_handler))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.photo_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_message_handler))
        # A fallback for any other message type
        self.app.add_handler(MessageHandler(~filters.COMMAND & ~filters.PHOTO & ~filters.TEXT, self.unsupported_message_handler))

    def _is_user_authorized(self, user_id):
        """Checks if a user is either an admin or an authorized guest."""
        return user_id in self.authorized_users or user_id in self.guest_users

    def _get_user_display_name(self, user):
        """Gets the display name for a user, preferring the guest name if available."""
        if user.id in self.guest_users:
            return self.guest_users[user.id]
        return user.first_name

    async def start_command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the /start and /help commands, including invitation code validation."""
        user = update.effective_user
        
        # Case 1: The /start command includes an invitation code (e.g., /start MyCode123)
        if context.args:
            code = context.args[0]
            logger.info(f"User {user.id} ({user.first_name}) is attempting to use invitation code: {code}")
            # The validation callback is a sync function from app.py
            result = self.validation_callback(code, user.id, user.first_name)
            await update.message.reply_text(result['message'])
            # If validation was successful, update the bot's internal guest list
            if result.get('success'):
                self.guest_users[user.id] = result.get('guest_name', user.first_name)
            return

        # Case 2: The user is already authorized
        if self._is_user_authorized(user.id):
            display_name = self._get_user_display_name(user)
            help_text = (
                f"👋 Bonjour {display_name} !\n\n"
                "Je suis le bot du cadre photo Pimmich. Voici comment m'utiliser :\n\n"
                "1️⃣ *Envoyez-moi une photo* pour l'afficher sur le cadre.\n"
                "2️⃣ *Ajoutez une légende* à votre photo pour qu'elle s'affiche en dessous.\n\n"
                "C'est tout ! Vos souvenirs apparaîtront comme par magie. ✨"
            )
            await update.message.reply_text(help_text, parse_mode=constants.ParseMode.MARKDOWN)
        # Case 3: The user is not authorized and did not provide a code
        else:
            logger.warning(f"Unauthorized user {user.id} ({user.first_name}) tried to use the bot.")
            unauthorized_text = (
                "🚫 Bonjour ! Pour envoyer des photos, vous avez besoin d'un code d'invitation.\n\n"
                "Veuillez demander le code à l'administrateur du cadre et envoyez-le moi directement, "
                "ou utilisez le lien d'invitation."
            )
            await update.message.reply_text(unauthorized_text)

    async def photo_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles photo messages from authorized users."""
        user = update.effective_user

        if not self._is_user_authorized(user.id):
            logger.warning(f"Unauthorized user {user.id} ({user.first_name}) tried to send a photo.")
            await update.message.reply_text("🚫 Désolé, vous n'êtes pas autorisé à envoyer de photos.")
            return

        display_name = self._get_user_display_name(user)
        await update.message.reply_text("📬 Photo bien reçue ! Traitement en cours...")

        try:
            photo = update.message.photo[-1]  # Highest resolution
            caption = update.message.caption or ""
            
            temp_dir = Path("cache/telegram_temp")
            temp_dir.mkdir(exist_ok=True)
            temp_photo_path = temp_dir / f"{user.id}_{photo.file_unique_id}.jpg"
            
            photo_file = await photo.get_file()
            await photo_file.download_to_drive(str(temp_photo_path))
            logger.info(f"Photo from {display_name} ({user.id}) downloaded to {temp_photo_path}")

            # Call the synchronous callback in a separate thread to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.photo_callback, str(temp_photo_path), caption, display_name)

            await update.message.reply_text("✅ Votre photo a été ajoutée au cadre !")
        except Exception as e:
            logger.error(f"Error processing photo from {user.id}: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Oups, une erreur est survenue lors du traitement de votre photo. L'administrateur a été notifié.")

    async def text_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles plain text messages, checking for potential invitation codes."""
        user = update.effective_user
        message_text = update.message.text.strip()

        # If user is already authorized, just give a helpful message
        if self._is_user_authorized(user.id):
            await update.message.reply_text("📷 Pour ajouter une photo, il suffit de me l'envoyer directement ! Vous pouvez y ajouter une légende.")
            return

        # If user is not authorized, treat the message as a potential invitation code
        logger.info(f"Potential invitation code '{message_text}' received from user {user.id} ({user.first_name}).")
        result = self.validation_callback(message_text, user.id, user.first_name)
        await update.message.reply_text(result['message'])
        
        # If validation was successful, update the bot's internal guest list
        if result.get('success'):
            self.guest_users[user.id] = result.get('guest_name', user.first_name)

    async def unsupported_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles any message type that is not a command, photo, or text."""
        user = update.effective_user
        if self._is_user_authorized(user.id):
            await update.message.reply_text("🤔 Je ne sais pas quoi faire avec ça. Essayez de m'envoyer une photo !")
        else:
            await update.message.reply_text("🚫 Pour commencer, veuillez m'envoyer votre code d'invitation.")

    def run(self):
        """
        Lance le bot en mode polling.
        Désactive les gestionnaires de signaux (stop_signals=None) car le bot tourne
        dans un thread secondaire, ce qui est nécessaire pour éviter une erreur au démarrage.
        """
        print("🤖 Bot Telegram Pimmich actif. En attente de messages...")
        self.app.run_polling(stop_signals=None)