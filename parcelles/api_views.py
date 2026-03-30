"""
Vues API GIS pour les parcelles — OPTIMISÉ PERFORMANCE ULTRA.

Optimisations :
  1. Cache Django conditionnel (ETag + Cache-Control pour public, no-cache pour auth)
  2. Simplification géométrique adaptative selon le zoom
  3. Prefetch optimisé (only/defer) pour réduire les requêtes SQL
  4. Sérialisation GeoJSON manuelle (bypass DRF pour les listes = 3-5x plus rapide)
  5. BBOX viewport filtering natif PostGIS
  6. Compression GZip automatique
  7. Annotations distance pour nearby (DB-level, pas Python)
"""
import hashlib
import json
import logging
import os
import shutil
import tempfile
import zipfile
from shapely.geometry import shape, mapping

from django.conf import settings
from django.core.cache import cache
from django.db.models import F, Q, Value, CharField, Prefetch
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.gzip import gzip_page

from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_gis.filters import InBBOXFilter
from django_filters.rest_framework import DjangoFilterBackend

from .models import Parcelle, ParcelleMedia, Zone, Ilot
from .serializers import (
    ParcelleListSerializer,
    ParcelleDetailSerializer,
    ZoneSerializer,
    IlotSerializer,
)

logger = logging.getLogger("parcelles")

# ═══════════════════════════════════════════════════════
#  CONSTANTES PERFORMANCE
# ═══════════════════════════════════════════════════════
GEOJSON_CACHE_TTL = 15          # secondes (court pour rester frais)
GEOJSON_PUBLIC_CACHE_TTL = 30   # secondes pour les reponses publiques (reduit pour visibilite rapide)
SIMPLIFY_THRESHOLDS = {
    # zoom_level: tolerance en degrés (WGS84)
    # IMPORTANT: tolerances réduites pour ne jamais faire disparaitre
    # les petites parcelles (<200m²) même au zoom le plus lointain.
    'overview': 0.00015,  # zoom < 10  → simplifié mais visible (~17m)
    'city':     0.00008,  # zoom 10-13 → légèrement simplifié (~9m)
    'detail':   0.00003,  # zoom 13-15 → quasi complet (~3m)
    'max':      0.0,      # zoom > 15  → géométrie complète
}


def _get_simplify_tolerance(zoom):
    """Retourne la tolérance de simplification selon le niveau de zoom.
    Tolérance réduite pour garantir que toutes les parcelles restent visibles
    quel que soit le zoom. Les petites parcelles (<200m²) ne disparaissent plus.
    """
    if zoom is None:
        return SIMPLIFY_THRESHOLDS['city']
    zoom = int(float(zoom))
    if zoom < 10:
        return SIMPLIFY_THRESHOLDS['overview']
    elif zoom < 13:
        return SIMPLIFY_THRESHOLDS['city']
    elif zoom < 15:
        return SIMPLIFY_THRESHOLDS['detail']
    return SIMPLIFY_THRESHOLDS['max']


def _build_cache_key(params, is_auth):
    """Construit une clé de cache déterministe à partir des paramètres.
    Inclut le compteur de version pour que l'invalidation fonctionne.
    """
    version = cache.get("geojson_version", 0)
    parts = sorted(params.items())
    parts.append(('_auth', str(is_auth)))
    parts.append(('_v', str(version)))
    raw = '&'.join(f'{k}={v}' for k, v in parts if v)
    return f"geojson:{hashlib.md5(raw.encode()).hexdigest()}"


def _parcelle_to_feature(p, is_authenticated, simplify_tolerance=0):
    """
    Sérialise un objet Parcelle en GeoJSON Feature dict — ULTRA RAPIDE.
    Bypass complet de DRF serializers (3-5x plus rapide).
    Garantit que chaque parcelle a toujours une géométrie valide :
    si la simplification produit une géométrie vide/nulle, on utilise
    le centroid comme point de fallback pour rester visible sur la carte.
    """
    # Géométrie (simplifiée ou complète)
    geom = p._simplified_geometry if hasattr(p, '_simplified_geometry') and p._simplified_geometry else p.geometry
    if geom is None:
        # Fallback: utiliser le centroid comme Point si pas de géométrie
        if p.centroid:
            geom = p.centroid
        else:
            return None

    try:
        geom_json = json.loads(geom.geojson)
    except Exception:
        # Si la géométrie simplifiée est invalide, fallback au centroid
        if p.centroid:
            geom_json = json.loads(p.centroid.geojson)
        else:
            return None

    # Propriétés publiques (toujours visibles)
    props = {
        'lot_number':        p.lot_number,
        'title':             p.title,
        'status':            p.status,
        'status_display':    p.get_status_display(),
        'land_type':         p.land_type,
        'land_type_display': p.get_land_type_display(),
        'surface_m2':        str(p.surface_m2) if p.surface_m2 else None,
        'price':             str(p.price) if p.price else '0',
        'price_per_m2':      str(p.price_per_m2) if p.price_per_m2 else None,
        'status_color':      {'disponible': '#059669', 'reserve': '#D97706', 'vendu': '#DC2626'}.get(p.status, '#6b7280'),
        'address':           p.address or '',
        'is_validated':      p.is_validated,
        'trust_badge':       p.trust_badge,
        'views_count':       p.views_count,
        'zone_name':         p.zone.name if p.zone_id else '',
    }

    # Image principale (prefetchée)
    main_img = ''
    if hasattr(p, '_prefetched_medias'):
        medias = p._prefetched_medias
    else:
        medias = list(p.medias.filter(media_type='image').order_by('order')[:1]) if hasattr(p, 'medias') else []
    if medias:
        try:
            main_img = medias[0].file.url if medias[0].file else ''
        except Exception:
            main_img = ''
    props['main_image'] = main_img

    # Propriétés RBAC (authentifié seulement)
    if is_authenticated:
        props['owner_name'] = p.owner.get_full_name() or p.owner.email if p.owner_id else ''
        props['owner_phone'] = getattr(p.owner, 'phone', '') if p.owner_id else ''
        props['description_display'] = (p.description or '')[:200]
        props['price_display'] = str(p.price) if p.price else '0'
        props['created_at_display'] = p.created_at.isoformat() if p.created_at else ''
    else:
        props['owner_name'] = None
        props['owner_phone'] = None
        props['description_display'] = None
        props['price_display'] = str(p.price) if p.price else '0'
        props['created_at_display'] = None

    return {
        'type': 'Feature',
        'id': str(p.pk),
        'geometry': geom_json,
        'properties': props,
    }


# ═══════════════════════════════════════════════════════
#  GEOJSON LIST — ENDPOINT PRINCIPAL CARTE
# ═══════════════════════════════════════════════════════

@gzip_page
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def parcelle_geojson_list(request):
    """
    Liste GeoJSON des parcelles pour la carte — OPTIMISÉ.

    Optimisations appliquées :
      - Cache Django avec TTL court (30s auth, 120s public)
      - ETag pour 304 Not Modified côté client
      - Simplification géométrique adaptative au zoom
      - Prefetch medias en 1 seule query
      - Sérialisation manuelle (bypass DRF = 3-5x speedup)
      - select_related + only() pour minimiser le SQL
      - GZip automatique
    """
    params = request.query_params
    is_auth = request.user.is_authenticated

    # ── Cache lookup ──
    cache_params = {k: v for k, v in params.items()}
    cache_key = _build_cache_key(cache_params, is_auth)

    cached = cache.get(cache_key)
    if cached:
        # ETag check
        etag = hashlib.md5(json.dumps(cached, sort_keys=True, default=str).encode()).hexdigest()
        if request.META.get('HTTP_IF_NONE_MATCH') == etag:
            return JsonResponse(status=304, data={})

        response = JsonResponse(cached, safe=True)
        response['ETag'] = etag
        if not is_auth:
            response['Cache-Control'] = f'public, max-age={GEOJSON_PUBLIC_CACHE_TTL}'
        else:
            response['Cache-Control'] = 'private, max-age=30'
        return response

    # ── QuerySet optimisé ──
    qs = Parcelle.objects.select_related("owner", "zone").filter(
        is_validated=True,
        geometry__isnull=False,
    ).only(
        'id', 'lot_number', 'title', 'description', 'status', 'land_type',
        'surface_m2', 'price', 'price_per_m2', 'address', 'is_validated',
        'trust_badge', 'views_count', 'geometry', 'centroid', 'created_at',
        'owner_id', 'owner__first_name', 'owner__last_name', 'owner__email', 'owner__phone',
        'zone_id', 'zone__name',
    )

    # ── Filtres ──
    search = params.get("search")
    if search:
        qs = qs.filter(
            Q(title__icontains=search) |
            Q(lot_number__icontains=search) |
            Q(address__icontains=search) |
            Q(zone__name__icontains=search)
        )

    status_filter = params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)

    land_type = params.get("land_type")
    if land_type:
        qs = qs.filter(land_type=land_type)

    zone_filter = params.get("zone")
    if zone_filter:
        qs = qs.filter(zone_id=zone_filter)

    price_min = params.get("price_min")
    price_max = params.get("price_max")
    if price_min:
        qs = qs.filter(price__gte=price_min)
    if price_max:
        qs = qs.filter(price__lte=price_max)

    surface_min = params.get("surface_min")
    surface_max = params.get("surface_max")
    if surface_min:
        qs = qs.filter(surface_m2__gte=surface_min)
    if surface_max:
        qs = qs.filter(surface_m2__lte=surface_max)

    # ── BBOX viewport filtering ──
    bbox = params.get("in_bbox")
    if bbox:
        try:
            from django.contrib.gis.geos import Polygon as GEOSPolygon
            coords = [float(c) for c in bbox.split(',')]
            if len(coords) == 4:
                bbox_poly = GEOSPolygon.from_bbox(coords)
                bbox_poly.srid = 4326
                qs = qs.filter(geometry__bboverlaps=bbox_poly)
        except (ValueError, TypeError, ImportError):
            pass

    # ── Simplification géométrique adaptative ──
    zoom = params.get("zoom")
    tolerance = _get_simplify_tolerance(zoom)
    if tolerance > 0:
        try:
            from django.contrib.gis.db.models.functions import SimplifyPreserveTopology
            qs = qs.annotate(
                _simplified_geometry=SimplifyPreserveTopology('geometry', tolerance)
            )
        except ImportError:
            pass  # Fallback: pas de simplification

    # ── Prefetch medias (1 query pour toutes les parcelles) ──
    media_qs = ParcelleMedia.objects.filter(media_type='image').order_by('order').only(
        'id', 'parcelle_id', 'file', 'media_type', 'order'
    )
    parcelles = list(qs.prefetch_related(
        Prefetch('medias', queryset=media_qs, to_attr='_prefetched_medias')
    ))

    # ── Sérialisation manuelle (3-5x plus rapide que DRF) ──
    features = []
    for p in parcelles:
        feat = _parcelle_to_feature(p, is_auth, tolerance)
        if feat:
            features.append(feat)

    result = {
        'type': 'FeatureCollection',
        'features': features,
        '_meta': {
            'count': len(features),
            'cached': False,
            'simplified': tolerance > 0,
            'zoom': zoom,
        }
    }

    # ── Mise en cache ──
    ttl = GEOJSON_CACHE_TTL if is_auth else GEOJSON_PUBLIC_CACHE_TTL
    cache.set(cache_key, result, ttl)

    # ── Réponse avec ETag ──
    etag = hashlib.md5(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()
    response = JsonResponse(result, safe=True)
    response['ETag'] = etag
    if not is_auth:
        response['Cache-Control'] = f'public, max-age={GEOJSON_PUBLIC_CACHE_TTL}'
    else:
        response['Cache-Control'] = 'private, max-age=30'

    return response


# ═══════════════════════════════════════════════════════
#  ANCIEN ENDPOINT (DRF) — conservé pour compatibilité
# ═══════════════════════════════════════════════════════

class ParcelleGeoListView(generics.ListAPIView):
    """Liste GeoJSON (DRF) — utilisé comme fallback."""
    serializer_class = ParcelleListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None
    filter_backends = [DjangoFilterBackend, InBBOXFilter]
    bbox_filter_field = "geometry"
    filterset_fields = ["status", "land_type", "zone", "is_validated"]

    def get_queryset(self):
        qs = Parcelle.objects.select_related("owner", "zone").filter(
            is_validated=True,
            geometry__isnull=False,
        )
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(lot_number__icontains=search) |
                Q(address__icontains=search) | Q(description__icontains=search) |
                Q(zone__name__icontains=search)
            )
        price_min = self.request.query_params.get("price_min")
        price_max = self.request.query_params.get("price_max")
        if price_min:
            qs = qs.filter(price__gte=price_min)
        if price_max:
            qs = qs.filter(price__lte=price_max)
        surface_min = self.request.query_params.get("surface_min")
        surface_max = self.request.query_params.get("surface_max")
        if surface_min:
            qs = qs.filter(surface_m2__gte=surface_min)
        if surface_max:
            qs = qs.filter(surface_m2__lte=surface_max)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def list(self, request, *args, **kwargs):
        try:
            response = super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Erreur API GeoJSON list: {e}", exc_info=True)
            response = Response({
                "type": "FeatureCollection", "features": [], "_error": str(e),
            })
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["Pragma"] = "no-cache"
        return response


class ParcelleGeoDetailView(generics.RetrieveAPIView):
    """Détail GeoJSON d'une parcelle."""
    serializer_class = ParcelleDetailSerializer
    permission_classes = [permissions.AllowAny]
    queryset = Parcelle.objects.select_related("owner", "owner__profile", "zone", "ilot")


# ═══════════════════════════════════════════════════════
#  NEARBY — Optimisé avec annotations distance DB-level
# ═══════════════════════════════════════════════════════

@gzip_page
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def nearby_parcelles(request):
    """Parcelles dans un rayon donné — distance calculée en DB."""
    from django.contrib.gis.geos import Point
    from django.contrib.gis.measure import D

    try:
        lat = float(request.query_params.get("lat"))
        lng = float(request.query_params.get("lng"))
        radius = float(request.query_params.get("radius", 5))
    except (TypeError, ValueError):
        return Response(
            {"error": "Paramètres lat, lng requis (radius optionnel, défaut 5km)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    limit = min(int(request.query_params.get("limit", 30)), 50)
    point = Point(lng, lat, srid=4326)

    # Distance calculée en DB (pas en Python) + tri + limite
    from django.contrib.gis.db.models.functions import Distance
    from django.db.models import Q

    # Filtrer sur geometry OU centroid pour couvrir les deux cas
    # Exclure les parcelles sans centroid pour éviter crash Distance()
    parcelles = (
        Parcelle.objects
        .filter(
            is_validated=True,
            centroid__isnull=False,
        )
        .filter(
            Q(geometry__distance_lte=(point, D(km=radius)))
            | Q(centroid__distance_lte=(point, D(km=radius)))
        )
        .select_related("zone")
        .annotate(
            distance=Distance('centroid', point),
        )
        .order_by('distance')
        .only(
            'id', 'lot_number', 'title', 'status', 'price',
            'surface_m2', 'land_type', 'centroid', 'address',
            'zone_id', 'zone__name',
        )[:limit]
    )

    results = []
    for p in parcelles:
        dist_m = p.distance.m if p.distance else None
        centroid = p.centroid
        results.append({
            'id': str(p.pk),
            'lot_number': p.lot_number,
            'title': p.title,
            'status': p.status,
            'price': str(p.price) if p.price else '0',
            'surface_m2': str(p.surface_m2) if p.surface_m2 else None,
            'land_type': p.land_type,
            'zone': p.zone.name if p.zone_id else '',
            'address': p.address or '',
            'lat': centroid.y if centroid else lat,
            'lng': centroid.x if centroid else lng,
            'distance_m': round(dist_m, 1) if dist_m else None,
        })

    return Response({'parcelles': results, 'count': len(results)})


# ═══════════════════════════════════════════════════════
#  CACHE INVALIDATION — Signal-based
# ═══════════════════════════════════════════════════════

def invalidate_geojson_cache():
    """Invalide tout le cache GeoJSON. Délègue aux signals pour l'auto-invalidation."""
    from parcelles.signals import invalidate_geojson_cache as _invalidate
    _invalidate()


# ═══════════════════════════════════════════════════════
#  ZONES & ILOTS
# ═══════════════════════════════════════════════════════

class ZoneListView(generics.ListAPIView):
    """Liste des zones (GeoJSON)."""
    serializer_class = ZoneSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None
    queryset = Zone.objects.all()


class IlotListView(generics.ListAPIView):
    """Liste des îlots (GeoJSON)."""
    serializer_class = IlotSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None
    queryset = Ilot.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        zone = self.request.query_params.get("zone")
        if zone:
            qs = qs.filter(zone_id=zone)
        return qs


# ═══════════════════════════════════════════════════════
#  SHAPEFILE PREVIEW
# ═══════════════════════════════════════════════════════

def _parse_shapefile_geopandas(file_path):
    """Parse un Shapefile (.shp/.zip) via geopandas avec reprojection auto."""
    import geopandas as gpd

    ext = os.path.splitext(file_path)[1].lower()
    is_zip = False
    try:
        is_zip = zipfile.is_zipfile(file_path)
    except Exception:
        pass

    if is_zip:
        extract_dir = tempfile.mkdtemp(prefix="eyefoncier_shp_")
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                zf.extractall(extract_dir)
            shp_path = None
            for root, dirs, files in os.walk(extract_dir):
                for fname in files:
                    if fname.lower().endswith(".shp") and not fname.startswith("."):
                        shp_path = os.path.join(root, fname)
                        break
                if shp_path:
                    break
            if not shp_path:
                raise ValueError("Aucun fichier .shp trouvé dans l'archive zip.")
            gdf = gpd.read_file(shp_path)
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)
    elif ext == ".shp":
        base = os.path.splitext(file_path)[0]
        if not (os.path.exists(base + ".shx") and os.path.exists(base + ".dbf")):
            raise ValueError("Fichier .shp seul. Uploadez un .zip contenant .shp, .shx et .dbf.")
        gdf = gpd.read_file(file_path)
    else:
        raise ValueError(f"Format non supporté: {os.path.basename(file_path)}")

    crs_info = str(gdf.crs) if gdf.crs else "Non défini (WGS84 supposé)"
    if gdf.crs and str(gdf.crs).lower() not in ("epsg:4326", "wgs 84", "wgs84"):
        gdf = gdf.to_crs(epsg=4326)

    features = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        props = {}
        for col in gdf.columns:
            if col == "geometry":
                continue
            v = row[col]
            if v is not None and str(v) != "nan":
                props[col] = str(v) if not isinstance(v, (int, float, bool)) else v
        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": props,
        })
    return features, crs_info


def _parse_dxf_file(file_path):
    """Parse un fichier DXF et extrait les polygones/polylines."""
    try:
        import ezdxf
    except ImportError:
        raise ValueError("Module ezdxf non installé. Installez-le : pip install ezdxf")

    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()
    features = []

    for entity in msp:
        coords = []
        etype = entity.dxftype()

        if etype == "LWPOLYLINE":
            coords = [(p[0], p[1]) for p in entity.get_points(format="xy")]
            if entity.closed and len(coords) >= 3:
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
        elif etype == "POLYLINE":
            coords = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
            if entity.is_closed and len(coords) >= 3:
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
        elif etype == "LINE":
            coords = [
                (entity.dxf.start.x, entity.dxf.start.y),
                (entity.dxf.end.x, entity.dxf.end.y),
            ]
        elif etype == "3DFACE":
            pts = [entity.dxf.vtx0, entity.dxf.vtx1, entity.dxf.vtx2, entity.dxf.vtx3]
            coords = [(p.x, p.y) for p in pts]
            if coords[0] != coords[-1]:
                coords.append(coords[0])

        if len(coords) >= 3:
            # Fermer le polygone si besoin
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            geom = {"type": "Polygon", "coordinates": [coords]}
            features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": {"layer": getattr(entity.dxf, "layer", "0"), "source": "DXF"},
            })

    if not features:
        raise ValueError("Aucun polygone trouvé dans le fichier DXF.")

    # Détection automatique : si les coordonnées semblent être en UTM (> 180°),
    # reprojeter de UTM Zone 30N vers WGS84
    first_coord = features[0]["geometry"]["coordinates"][0][0]
    if abs(first_coord[0]) > 180 or abs(first_coord[1]) > 180:
        try:
            import pyproj
            from shapely.ops import transform as shapely_transform
            transformer = pyproj.Transformer.from_crs("EPSG:32630", "EPSG:4326", always_xy=True)
            for feat in features:
                geom = shape(feat["geometry"])
                geom_wgs = shapely_transform(transformer.transform, geom)
                feat["geometry"] = mapping(geom_wgs)
        except ImportError:
            raise ValueError("Coordonnées en projection locale détectées mais pyproj n'est pas installé pour la reprojection.")

    return features, "DXF (reprojection auto UTM30N → WGS84 si nécessaire)"


def _parse_txt_coordinates(file_path):
    """Parse un fichier TXT de coordonnées géométriques.

    Formats supportés :
      - X Y (ou X,Y ou X;Y ou X\tY) — un point par ligne
      - N X Y (numéro de point, X, Y)
      - N X Y Z (numéro de point, X, Y, Z)
    """
    coords = []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            # Normaliser les séparateurs
            parts = line.replace(",", " ").replace(";", " ").replace("\t", " ").split()
            parts = [p for p in parts if p]

            try:
                if len(parts) == 2:
                    x, y = float(parts[0]), float(parts[1])
                elif len(parts) == 3:
                    # N X Y ou X Y Z
                    try:
                        _ = int(parts[0])  # Si c'est un entier → c'est un numéro de point
                        x, y = float(parts[1]), float(parts[2])
                    except ValueError:
                        x, y = float(parts[0]), float(parts[1])
                elif len(parts) >= 4:
                    # N X Y Z
                    try:
                        _ = int(parts[0])
                        x, y = float(parts[1]), float(parts[2])
                    except ValueError:
                        x, y = float(parts[0]), float(parts[1])
                else:
                    continue
                coords.append((x, y))
            except (ValueError, IndexError):
                continue

    if len(coords) < 3:
        raise ValueError(f"Minimum 3 points requis pour former un polygone. Trouvé : {len(coords)} point(s).")

    # Fermer le polygone
    if coords[0] != coords[-1]:
        coords.append(coords[0])

    # Détection : UTM ou WGS84 ?
    is_utm = abs(coords[0][0]) > 180 or abs(coords[0][1]) > 180
    crs_info = "Coordonnées brutes"

    if is_utm:
        try:
            import pyproj
            from shapely.ops import transform as shapely_transform
            transformer = pyproj.Transformer.from_crs("EPSG:32630", "EPSG:4326", always_xy=True)
            geom = shape({"type": "Polygon", "coordinates": [coords]})
            geom_wgs = shapely_transform(transformer.transform, geom)
            coords = list(geom_wgs.exterior.coords)
            crs_info = "UTM Zone 30N → WGS84 (reprojection auto)"
        except ImportError:
            raise ValueError("Coordonnées UTM détectées mais pyproj n'est pas installé.")

    feature = {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [list(coords)]},
        "properties": {"source": "TXT", "points_count": len(coords) - 1},
    }
    return [feature], crs_info


def _parse_xy_coordinates(xy_text):
    """Parse des coordonnées X,Y saisies manuellement (texte brut).

    Même logique que _parse_txt_coordinates mais depuis une chaîne.
    """
    import io
    tmpdir = tempfile.mkdtemp(prefix="eyefoncier_xy_")
    try:
        tmp_path = os.path.join(tmpdir, "coords.txt")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(xy_text)
        return _parse_txt_coordinates(tmp_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def shapefile_preview(request):
    """Prévisualise un fichier uploadé (Shapefile, DXF, TXT) ou des coordonnées X,Y.

    Supporte :
      - Shapefile (.shp/.zip) via geopandas
      - DXF (.dxf) via ezdxf
      - TXT (.txt/.csv) — fichier de coordonnées géométriques
      - Coordonnées brutes (paramètre POST 'coordinates')
    """
    # Mode coordonnées textuelles (pas de fichier)
    coord_text = request.data.get("coordinates", "").strip()
    if coord_text:
        try:
            features, crs_info = _parse_xy_coordinates(coord_text)
            return Response({
                "type": "FeatureCollection",
                "features": features,
                "crs_info": crs_info,
                "count": len(features),
                "format": "coordinates",
            })
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

    shp_file = request.FILES.get("file")
    if not shp_file:
        return Response({"error": "Aucun fichier fourni."}, status=status.HTTP_400_BAD_REQUEST)

    tmpdir = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="eyefoncier_preview_")
        safe_name = shp_file.name.replace(" ", "_")
        tmp_path = os.path.join(tmpdir, safe_name)
        with open(tmp_path, "wb") as f:
            for chunk in shp_file.chunks():
                f.write(chunk)

        ext = os.path.splitext(safe_name)[1].lower()
        file_format = "unknown"

        if ext in (".shp", ".zip"):
            features, crs_info = _parse_shapefile_geopandas(tmp_path)
            file_format = "shapefile"
        elif ext == ".dxf":
            features, crs_info = _parse_dxf_file(tmp_path)
            file_format = "dxf"
        elif ext in (".txt", ".csv", ".pts", ".coord"):
            features, crs_info = _parse_txt_coordinates(tmp_path)
            file_format = "txt"
        else:
            # Tenter geopandas en dernier recours
            try:
                features, crs_info = _parse_shapefile_geopandas(tmp_path)
                file_format = "auto"
            except Exception:
                return Response({
                    "error": f"Format non supporté : {ext}. Formats acceptés : .shp, .zip, .dxf, .txt"
                }, status=400)

        return Response({
            "type": "FeatureCollection",
            "features": features,
            "crs_info": crs_info,
            "count": len(features),
            "format": file_format,
        })
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.error(f"Erreur preview multi-format: {e}", exc_info=True)
        return Response({"error": f"Erreur : {str(e)}"}, status=400)
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
