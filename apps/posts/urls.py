from django.urls import path
from apps.posts.views import (
    ChannelPostListView,
    PostListCreateView,
    PostDetailView,
    PostViewTrackView,
    PinnedPostsView,
    SearchPostsView
)

app_name = "posts"

urlpatterns = [
    # Dashboard — owner's posts across all channels
    path("", PostListCreateView.as_view(), name="post-list-create"),
    path("<uuid:post_id>/", PostDetailView.as_view(), name="post-detail"),
    path(
        "<uuid:post_id>/view/",
        PostViewTrackView.as_view(),
        name="post-view-track",
    ),

    # Public channel feed
    path(
        "channel/<slug:slug>/",
        ChannelPostListView.as_view(),
        name="channel-post-list",
    ),
    path(
        "channel/<slug:slug>/pinned/",
        PinnedPostsView.as_view(),
        name="channel-pinned-posts",
    ),
    path(
        "search/",
        SearchPostsView.as_view(),
        name="post-search",
    ),
]