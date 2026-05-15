from django.urls import path
from apps.channels.views import (
    ChannelListCreateView,
    ChannelDetailView,
    ChannelTelegramLinkView,
    ChannelAnalyticsView,
    MyChannelsView,
)

app_name = "channels"

urlpatterns = [
    path("", ChannelListCreateView.as_view(), name="channel-list-create"),
    path("mine/", MyChannelsView.as_view(), name="my-channels"),
    path("<slug:slug>/", ChannelDetailView.as_view(), name="channel-detail"),
    path(
        "<slug:slug>/link-telegram/",
        ChannelTelegramLinkView.as_view(),
        name="channel-link-telegram",
    ),
    path(
        "<slug:slug>/analytics/",
        ChannelAnalyticsView.as_view(),
        name="channel-analytics",
    ),
]