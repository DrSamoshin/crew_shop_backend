"""Ratings ORM models. Importing this package registers the mappers on ``Base.metadata``."""

from src.ratings.models.product_rating import ProductRating
from src.ratings.models.rating import Rating

__all__ = ["ProductRating", "Rating"]
