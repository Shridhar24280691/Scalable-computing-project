import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework import status
from .models import Review
from .serializers import ReviewSerializer

# Use your own key here
OPEN_TRIPMAP_API_KEY = "5ae2e3f221c38a28845f05b6120c9b42b4fb3a54edcb7e9f05310aeb"


def _get_restaurant_results(city, cuisine, budget, limit):
    """
    Call OpenTripMap (geoname + radius) and return a dict:
    { city, cuisine, budget, count, restaurants, [error] }
    """

    base = {
        "city": city,
        "cuisine": cuisine,
        "budget": budget,
        "count": 0,
        "restaurants": [],
    }

    try:
        # 1) Geocode the city
        geocode_url = "https://api.opentripmap.com/0.1/en/places/geoname"
        geo_res = requests.get(
            geocode_url,
            params={"name": city, "apikey": OPEN_TRIPMAP_API_KEY},
            timeout=5,
        )
        if geo_res.status_code != 200:
            base["error"] = f"Geocode error: {geo_res.status_code}"
            return base

        geo_data = geo_res.json()          # <-- this is a dict (you saw it in the browser)
        lat = geo_data.get("lat")
        lon = geo_data.get("lon")
        if lat is None or lon is None:
            base["error"] = "City not found in OpenTripMap"
            return base

        # 2) Radius search around that point
        radius_url = "https://api.opentripmap.com/0.1/en/places/radius"
        radius_res = requests.get(
            radius_url,
            params={
                "radius": 1000,          # metres around city centre
                "lon": lon,
                "lat": lat,
                "rate": 2,               # popularity
                "format": "json",        # IMPORTANT: this makes the response a LIST
                "limit": limit,
                "apikey": OPEN_TRIPMAP_API_KEY,
            },
            timeout=5,
        )
        if radius_res.status_code != 200:
            base["error"] = f"Places error: {radius_res.status_code}"
            return base

        # format=json -> radius_res.json() is a LIST, as in your screenshot
        places = radius_res.json()
        # Example element (from your screenshot):
        # {
        #   "xid": "N516789822",
        #   "name": "Catherine McAuley",
        #   "rate": 3,
        #   "point": { "lon": -6.24565, "lat": 53.33429 },
        #   ...
        # }

        restaurants = []
        for p in places:
            if not isinstance(p, dict):
                continue  # safety

            name = p.get("name")
            if not name:
                continue

            point = p.get("point") or {}
            lat_val = point.get("lat")
            lon_val = point.get("lon")

            restaurants.append(
                {
                    "id": p.get("xid"),
                    "name": name,
                    "city": city,
                    "address": "",  # full address would need a second details call
                    "lat": lat_val,
                    "lon": lon_val,
                    "cuisine": cuisine or "unknown",
                    "rating": p.get("rate", 0),
                    "price_level": 0,
                    "source": "opentripmap",
                }
            )

        base["count"] = len(restaurants)
        base["restaurants"] = restaurants
        return base

    except requests.RequestException as e:
        base["error"] = f"RequestException: {e}"
        return base
    except Exception as e:
        # This is where your "'list' object has no attribute 'get'" came from before.
        # With the code above, there is no .get() on a list anymore.
        base["error"] = f"Unexpected error: {e}"
        return base


@api_view(["GET"])
@permission_classes([IsAuthenticatedOrReadOnly])
def search_restaurants(request):
    city = request.query_params.get("city", "Dublin")
    cuisine = request.query_params.get("cuisine", "")
    budget = request.query_params.get("budget", "medium")
    limit = int(request.query_params.get("limit", "10"))

    data = _get_restaurant_results(city, cuisine, budget, limit)
    return Response(data, status=status.HTTP_200_OK)


@api_view(["GET"])
def recommendations(request):
    city = request.query_params.get("city", "Dublin")
    cuisine = request.query_params.get("cuisine", "")
    budget = request.query_params.get("budget", "medium")
    limit = int(request.query_params.get("limit", "5"))

    data = _get_restaurant_results(city, cuisine, budget, limit)
    return Response(data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_review(request, restaurant_id):
    data = request.data.copy()
    data["restaurant"] = restaurant_id
    data["user"] = request.user.id
    serializer = ReviewSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def draw_random_card(request):
    card_api_url = "https://friend-api-url/cards/random"
    card_res = requests.get(card_api_url, timeout=3)
    card_res.raise_for_status()
    card_data = card_res.json()

    city = request.query_params.get("city", "Dublin")
    rec_data = _get_restaurant_results(city=city, cuisine="", budget="medium", limit=1)
    restaurant = rec_data["restaurants"][0] if rec_data["restaurants"] else None

    return Response(
        {
            "card": card_data,
            "restaurant": restaurant,
        }
    )
