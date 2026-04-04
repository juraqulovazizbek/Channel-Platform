from django.urls import path
from apps.analytics.views import ChannelStatsView, TopPostsView

app_name = "analytics"

urlpatterns = [
    path(
        "channels/<slug:slug>/",
        ChannelStatsView.as_view(),
        name="channel-stats",
    ),
    path(
        "channels/<slug:slug>/top-posts/",
        TopPostsView.as_view(),
        name="channel-top-posts",
    ),
]