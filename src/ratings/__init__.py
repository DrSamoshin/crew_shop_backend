"""Ratings domain: individual 1-5 star product ratings and their denormalized aggregate.

Scope here is the data layer + aggregate recomputation. The rating-submission API,
purchase verification, and purchase-weighted averaging are the full Ratings feature
(they depend on Orders) and are deferred. The catalog reads the aggregate read-only.
"""
