import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework import status
from .models import Review
from .serializers import ReviewSerializer

OPEN_TRIPMAP_API_KEY = "5ae2e3f221c38a28845f05b6120c9b42b4fb3a54edcb7e9f05310aeb"
GEOAPIFY_API_KEY = "6b6902edc8c74644b40c0738a010e7d9"


def _get_restaurant_results(city, cuisine, budget, limit):

    base = {
        "city": city,
        "cuisine": cuisine,
        "budget": budget,
        "count": 0,
        "restaurants": [],
    }

    try:
        # Geocode city with OpenTripMap 
        geocode_url = "https://api.opentripmap.com/0.1/en/places/geoname"
        geo_res = requests.get(
            geocode_url,
            params={"name": city, "apikey": OPEN_TRIPMAP_API_KEY},
            timeout=5,
        )
        if geo_res.status_code != 200:
            base["error"] = f"Geocode error: {geo_res.status_code}"
            return base

        geo_data = geo_res.json()
        lat = geo_data.get("lat")
        lon = geo_data.get("lon")
        if lat is None or lon is None:
            base["error"] = "City not found in OpenTripMap"
            return base

        # Fetches restaurants with Geoapify
        places_url = "https://api.geoapify.com/v2/places"

        # Base category: all restaurants
        categories = "catering.restaurant"

        # Optional cuisine-specific category, with safe fallback
        cuisine_key = (cuisine or "").strip().lower()
        use_fallback = False
        if cuisine_key:
            categories = f"catering.restaurant.{cuisine_key}"
            use_fallback = True

        def query_geoapify(categories_value):
            params = {
                "categories": categories_value,
                "filter": f"circle:{lon},{lat},2000",  # 2km radius
                "limit": limit,
                "apiKey": GEOAPIFY_API_KEY,
            }
            return requests.get(places_url, params=params, timeout=8)

        # First attempt: with specific category (if cuisine provided)
        places_res = query_geoapify(categories)
        data = places_res.json() if places_res.status_code == 200 else {}

        # If cuisine-specific search returns nothing, fallback to all restaurants
        features = data.get("features") or []
        if use_fallback and (places_res.status_code != 200 or not features):
            places_res = query_geoapify("catering.restaurant")
            data = places_res.json() if places_res.status_code == 200 else {}
            features = data.get("features") or []

        if places_res.status_code != 200:
            base["error"] = f"Geoapify error: {places_res.status_code}"
            return base

        restaurants = []
        for f in features:
            if not isinstance(f, dict):
                continue

            props = f.get("properties", {})
            geom = f.get("geometry", {})

            name = props.get("name")
            if not name:
                continue

            coords = geom.get("coordinates", [None, None])
            lon_val, lat_val = coords[0], coords[1]

            address = (
                props.get("address_line1")
                or props.get("street")
                or props.get("formatted")
                or ""
            )

            restaurants.append(
                {
                    "id": props.get("place_id"),
                    "name": name,
                    "city": city,
                    "address": address,
                    "lat": lat_val,
                    "lon": lon_val,
                    "cuisine": cuisine or "restaurant",
                    "rating": props.get("rank", 0),  # popularity score
                    "price_level": 0,
                    "source": "geoapify",
                }
            )

        base["count"] = len(restaurants)
        base["restaurants"] = restaurants
        return base

    except requests.RequestException as e:
        base["error"] = f"RequestException: {e}"
        return base
    except Exception as e:
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
