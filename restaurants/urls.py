from django.urls import path
from . import views

urlpatterns = [
    path("search/", views.search_restaurants, name="search_restaurants"),
    path("recommendations/", views.recommendations, name="recommendations"),
    path("<int:restaurant_id>/reviews/", views.add_review, name="add_review"),
    path("draw-card/", views.draw_random_card, name="draw_card"),
]
