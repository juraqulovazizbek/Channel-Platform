from django.contrib import admin


# Bot app has no database models of its own.
# All bot-related data lives in Posts, Channels, and Users.
# This file exists to satisfy Django's app registry expectations.
#
# If you later add BotSession or BotCommand models,
# register them here.