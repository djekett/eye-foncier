"""Formulaires de gestion des parcelles — EYE-FONCIER.
Phase 2 : Support UTM Zone 30N + WGS84, import Shapefile robuste via GDAL/fiona.
"""
from django import forms
from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.core.exceptions import ValidationError
import json
import os
import tempfile
import zipfile
import logging

from .models import Parcelle, ParcelleMedia, Zone

logger = logging.getLogger("parcelles")


class ParcelleForm(forms.ModelForm):
    """Formulaire de création / modification d'une parcelle.

    Modes de saisie géométrique :
      1. Dessin sur carte (geometry_json via Leaflet Draw)
      2. Coordonnées textuelles — WGS84 (Lat/Lon) ou UTM Zone 30N (X/Y)
      3. Import Shapefile (.zip)
    """

    # ─── Champ caché : GeoJSON du polygone ───
    geometry_json = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
        help_text="GeoJSON de la géométrie (rempli automatiquement par la carte).",
    )

    # ─── Coordonnées textuelles (N sommets, format JSON) ───
    coordinates_text = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
        help_text="JSON array de coordonnées [[x,y], ...]",
    )

    # ─── Système de coordonnées ───
    COORD_SYSTEM_CHOICES = [
        ("wgs84", "WGS84 — GPS (Longitude, Latitude)"),
        ("utm30n", "UTM Zone 30N — Topographique (X, Y)"),
    ]
    coordinate_system = forms.ChoiceField(
        choices=COORD_SYSTEM_CHOICES,
        initial="wgs84",
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_coordinate_system"}),
        help_text="Système de coordonnées utilisé pour la saisie.",
    )

    # ─── Import Shapefile ────────────────────────
    shapefile_zip = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": ".zip,.shp",
        }),
        help_text="Archive .zip contenant les fichiers .shp, .shx, .dbf (et optionnellement .prj).",
    )

    # ─── Import DXF (AutoCAD) ────────────────────
    dxf_file = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": ".dxf",
        }),
        help_text="Fichier AutoCAD DXF contenant la géométrie de la parcelle.",
    )

    # ─── Import TXT / CSV coordonnées ────────────
    coords_file = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": ".txt,.csv,.xyz",
        }),
        help_text="Fichier texte de coordonnées (X Y par ligne, séparateur : espace/tabulation/virgule/point-virgule).",
    )

    class Meta:
        model = Parcelle
        fields = [
            "title", "lot_number", "ilot_number", "description", "land_type",
            "surface_m2", "price", "address", "title_holder_name",
            "cadastre_ref", "access_road", "water_access", "electricity",
            "topography", "soil_type",
            "zone", "ilot", "geometry_json",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "lot_number": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "land_type": forms.Select(attrs={"class": "form-select"}),
            "surface_m2": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "price": forms.NumberInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "title_holder_name": forms.TextInput(attrs={"class": "form-control"}),
            "zone": forms.Select(attrs={"class": "form-select"}),
            "ilot": forms.Select(attrs={"class": "form-select"}),
            "ilot_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Îlot 15"}),
            "cadastre_ref": forms.TextInput(attrs={"class": "form-control", "placeholder": "Réf. cadastrale officielle"}),
            "access_road": forms.Select(attrs={"class": "form-select"}),
            "water_access": forms.NullBooleanSelect(attrs={"class": "form-select"}),
            "electricity": forms.NullBooleanSelect(attrs={"class": "form-select"}),
            "topography": forms.Select(attrs={"class": "form-select"}),
            "soil_type": forms.Select(attrs={"class": "form-select"}),
        }

    # ─────────────────────────────────────────────────────────
    # Validation GeoJSON
    # ─────────────────────────────────────────────────────────
    def clean_geometry_json(self):
        geojson = self.cleaned_data.get("geometry_json")
        if geojson:
            try:
                geom = GEOSGeometry(geojson, srid=4326)
                if geom.geom_type not in ("Polygon", "MultiPolygon"):
                    raise forms.ValidationError("La géométrie doit être un polygone.")
                if geom.geom_type == "MultiPolygon":
                    geom = geom[0]
                return geom
            except forms.ValidationError:
                raise
            except Exception as e:
                raise forms.ValidationError(f"GeoJSON invalide : {e}")
        return None

    # ─────────────────────────────────────────────────────────
    # Conversion UTM Zone 30N → WGS84
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def _utm30n_to_wgs84(x, y):
        """Convertit des coordonnées UTM Zone 30N (EPSG:32630) → WGS84 (EPSG:4326).
        Retourne (longitude, latitude).
        """
        try:
            import pyproj
            transformer = pyproj.Transformer.from_crs(
                "EPSG:32630", "EPSG:4326", always_xy=True,
            )
            lng, lat = transformer.transform(x, y)
            return lng, lat
        except ImportError:
            raise forms.ValidationError(
                "La bibliothèque pyproj est requise pour la conversion UTM. "
                "Installez-la : pip install pyproj"
            )
        except Exception as e:
            raise forms.ValidationError(f"Erreur de conversion UTM→WGS84 : {e}")

    # ─────────────────────────────────────────────────────────
    # Construction du polygone depuis coordonnées textuelles
    # ─────────────────────────────────────────────────────────
    def _build_polygon_from_coordinates_text(self):
        """Construit un polygone à partir du champ coordinates_text.
        Gère WGS84 (lng, lat) et UTM Zone 30N (X, Y) selon coordinate_system.
        """
        raw = self.cleaned_data.get("coordinates_text", "").strip()
        if not raw:
            return None

        coord_system = self.cleaned_data.get("coordinate_system", "wgs84")

        try:
            coords = json.loads(raw)
            if not isinstance(coords, list) or len(coords) < 3:
                return None

            validated = []
            for pt in coords:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    x_val, y_val = float(pt[0]), float(pt[1])

                    if coord_system == "utm30n":
                        # Conversion UTM Zone 30N → WGS84
                        lng, lat = self._utm30n_to_wgs84(x_val, y_val)
                    else:
                        # Déjà en WGS84 (lng, lat)
                        lng, lat = x_val, y_val

                    # Validation basique des bornes WGS84
                    if not (-180 <= lng <= 180 and -90 <= lat <= 90):
                        logger.warning(
                            f"Coordonnée hors bornes WGS84 : lng={lng}, lat={lat}"
                        )
                        continue

                    validated.append((lng, lat))

            if len(validated) < 3:
                return None

            # Fermer le polygone si nécessaire
            if validated[0] != validated[-1]:
                validated.append(validated[0])

            poly = Polygon(validated, srid=4326)
            if not poly.valid:
                logger.warning("Polygone invalide, tentative make_valid via buffer(0)")
                poly = poly.buffer(0)
                if hasattr(poly, "geom_type") and poly.geom_type == "Polygon":
                    return poly
                return None
            return poly

        except forms.ValidationError:
            raise
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(f"Erreur parsing coordonnées textuelles: {e}")
            return None

    # ─────────────────────────────────────────────────────────
    # Import Shapefile (via fiona + GDAL fallback)
    # ─────────────────────────────────────────────────────────
    def _parse_shapefile(self):
        """Extrait la géométrie et les attributs d'un Shapefile uploadé.
        Utilise geopandas (avec reprojection automatique) — fallback fiona si disponible.
        """
        shp_file = self.cleaned_data.get("shapefile_zip")
        if not shp_file:
            return None, {}

        tmpdir = None
        try:
            from shapely.geometry import mapping
            from django.contrib.gis.geos import GEOSGeometry

            tmpdir = tempfile.mkdtemp(prefix="eyefoncier_shp_")
            safe_name = shp_file.name.replace(" ", "_")
            tmp_path = os.path.join(tmpdir, safe_name)
            with open(tmp_path, "wb") as f:
                for chunk in shp_file.chunks():
                    f.write(chunk)

            # Extraire le zip si nécessaire
            shp_path = tmp_path
            if zipfile.is_zipfile(tmp_path):
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    zf.extractall(tmpdir)
                # Trouver le .shp extrait
                for root, dirs, files in os.walk(tmpdir):
                    for fname in files:
                        if fname.lower().endswith(".shp") and not fname.startswith("."):
                            shp_path = os.path.join(root, fname)
                            break

            # Lire avec geopandas (ne dépend PAS de fiona pour les shapefiles)
            import geopandas as gpd
            gdf = gpd.read_file(shp_path)
            logger.info(f"Shapefile lu: {len(gdf)} features, CRS: {gdf.crs}")

            # Reprojeter en WGS84 si nécessaire
            if gdf.crs and str(gdf.crs).lower() not in ("epsg:4326", "wgs 84", "wgs84"):
                gdf = gdf.to_crs(epsg=4326)
                logger.info("Reprojection vers WGS84 effectuée")

            # Extraire la première géométrie polygonale
            attributes = {}
            geometry = None
            for idx, row in gdf.iterrows():
                geom = row.geometry
                if geom and geom.geom_type in ("Polygon", "MultiPolygon"):
                    if geom.geom_type == "MultiPolygon":
                        geom = list(geom.geoms)[0]

                    geojson_str = json.dumps(mapping(geom))
                    geometry = GEOSGeometry(geojson_str, srid=4326)

                    # Récupérer les attributs
                    attributes = {
                        k: v for k, v in row.drop("geometry").to_dict().items()
                        if v is not None and str(v) != "nan"
                    }
                    break

            return geometry, attributes

        except ImportError as e:
            logger.error(f"Dépendance manquante pour Shapefile: {e}")
            self.add_error("shapefile_zip", f"Module requis non installé : {e.name}. Contactez l'administrateur.")
            return None, {}
        except Exception as e:
            logger.error(f"Erreur lecture Shapefile: {e}", exc_info=True)
            self.add_error("shapefile_zip", f"Erreur de lecture du fichier : {e}")
            return None, {}
        finally:
            if tmpdir:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)

    # NOTE: Les anciennes méthodes fiona (_resolve_shapefile_path, _open_fiona_handle,
    # _get_reproject_func) ont été supprimées. geopandas gère la lecture et la
    # reprojection automatiquement via to_crs().

    # ─────────────────────────────────────────────────────────
    # Import DXF (AutoCAD)
    # ─────────────────────────────────────────────────────────
    def _parse_dxf(self):
        """Extrait la géométrie d'un fichier DXF (AutoCAD).
        Cherche les polylignes fermées (LWPOLYLINE, POLYLINE) ou les entités de surface.
        """
        dxf_file = self.cleaned_data.get("dxf_file")
        if not dxf_file:
            return None

        tmpdir = None
        try:
            import ezdxf

            tmpdir = tempfile.mkdtemp(prefix="eyefoncier_dxf_")
            tmp_path = os.path.join(tmpdir, dxf_file.name.replace(" ", "_"))
            with open(tmp_path, "wb") as f:
                for chunk in dxf_file.chunks():
                    f.write(chunk)

            doc = ezdxf.readfile(tmp_path)
            msp = doc.modelspace()
            coord_system = self.cleaned_data.get("coordinate_system", "wgs84")

            # Chercher les polylignes fermées
            for entity in msp:
                coords = []
                if entity.dxftype() == "LWPOLYLINE":
                    coords = [(p[0], p[1]) for p in entity.get_points()]
                elif entity.dxftype() == "POLYLINE":
                    coords = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                elif entity.dxftype() == "LINE":
                    coords = [
                        (entity.dxf.start.x, entity.dxf.start.y),
                        (entity.dxf.end.x, entity.dxf.end.y),
                    ]
                elif entity.dxftype() in ("3DFACE", "SOLID"):
                    try:
                        coords = [(entity.dxf.vtx0.x, entity.dxf.vtx0.y),
                                  (entity.dxf.vtx1.x, entity.dxf.vtx1.y),
                                  (entity.dxf.vtx2.x, entity.dxf.vtx2.y)]
                        if hasattr(entity.dxf, 'vtx3'):
                            coords.append((entity.dxf.vtx3.x, entity.dxf.vtx3.y))
                    except Exception:
                        continue

                if len(coords) >= 3:
                    # ═══ AUTO-DÉTECTION UTM ═══
                    # Si une coordonnée dépasse 180, ce n'est PAS du WGS84
                    # → forcer la conversion UTM Zone 30N (standard Côte d'Ivoire)
                    max_val = max(max(abs(x), abs(y)) for x, y in coords)
                    if max_val > 180 and coord_system == "wgs84":
                        logger.info(
                            "DXF: coordonnées > 180 détectées (max=%.0f) "
                            "→ conversion automatique UTM Zone 30N",
                            max_val,
                        )
                        coord_system = "utm30n"

                    # Convertir si UTM
                    if coord_system == "utm30n":
                        converted = []
                        for x, y in coords:
                            try:
                                lng, lat = self._utm30n_to_wgs84(x, y)
                                converted.append((lng, lat))
                            except Exception as e:
                                logger.warning("Erreur conversion UTM (%s, %s): %s", x, y, e)
                                continue
                        coords = converted

                    # Fermer le polygone
                    if coords[0] != coords[-1]:
                        coords.append(coords[0])

                    try:
                        poly = Polygon(coords, srid=4326)
                        if poly.valid:
                            logger.info("DXF importé: %d sommets", len(coords) - 1)
                            return poly
                        # Tenter de réparer
                        poly = poly.buffer(0)
                        if hasattr(poly, "geom_type") and poly.geom_type == "Polygon":
                            return poly
                    except Exception as e:
                        logger.warning("Polygone DXF invalide: %s", e)
                        continue

            logger.warning("Aucun polygone trouvé dans le DXF")
            return None

        except ImportError:
            logger.warning("ezdxf non installé — import DXF impossible")
            self.add_error("dxf_file", "La bibliothèque ezdxf est requise : pip install ezdxf")
            return None
        except Exception as e:
            logger.error("Erreur lecture DXF: %s", e, exc_info=True)
            self.add_error("dxf_file", "Erreur lecture DXF : {}".format(str(e)[:200]))
            return None
        finally:
            if tmpdir:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)

    # ─────────────────────────────────────────────────────────
    # Import fichier TXT/CSV de coordonnées
    # ─────────────────────────────────────────────────────────
    def _parse_coords_file(self):
        """Importe des coordonnées depuis un fichier texte (TXT, CSV, XYZ).

        Formats supportés :
          - X Y (séparés par espace, tab, virgule ou point-virgule)
          - X,Y
          - X;Y
          - N° X Y (numéro de point ignoré)
          - Lignes commençant par # ignorées (commentaires)
        """
        coords_file = self.cleaned_data.get("coords_file")
        if not coords_file:
            return None

        try:
            import re
            content = coords_file.read().decode("utf-8", errors="replace")
            coord_system = self.cleaned_data.get("coordinate_system", "wgs84")

            coords = []
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("//"):
                    continue

                # Séparer par espace, tab, virgule ou point-virgule
                parts = re.split(r'[,;\t\s]+', line)

                # Filtrer les parties numériques
                numbers = []
                for p in parts:
                    p = p.strip()
                    try:
                        numbers.append(float(p))
                    except ValueError:
                        continue

                if len(numbers) >= 2:
                    # Prendre les 2 premiers nombres (ou les 2 derniers si N° X Y)
                    if len(numbers) == 2:
                        x_val, y_val = numbers[0], numbers[1]
                    else:
                        # Si 3+ nombres, prendre index 1 et 2 (cas N° X Y)
                        # ou 0 et 1 si le premier est clairement une coordonnée
                        if numbers[0] < 100:  # probablement un numéro de point
                            x_val, y_val = numbers[1], numbers[2]
                        else:
                            x_val, y_val = numbers[0], numbers[1]

                    if coord_system == "utm30n":
                        lng, lat = self._utm30n_to_wgs84(x_val, y_val)
                    else:
                        lng, lat = x_val, y_val

                    if -180 <= lng <= 180 and -90 <= lat <= 90:
                        coords.append((lng, lat))

            if len(coords) < 3:
                if coords:
                    self.add_error(
                        "coords_file",
                        "Seulement {} point(s) trouvé(s). Minimum 3 pour un polygone.".format(len(coords)),
                    )
                return None

            # ═══ AUTO-DÉTECTION UTM ═══
            max_val = max(max(abs(x), abs(y)) for x, y in coords)
            if max_val > 180 and coord_system == "wgs84":
                logger.info(
                    "TXT: coordonnées > 180 détectées (max=%.0f) "
                    "→ re-conversion automatique UTM Zone 30N",
                    max_val,
                )
                reconverted = []
                for x_val, y_val in coords:
                    lng, lat = self._utm30n_to_wgs84(x_val, y_val)
                    if -180 <= lng <= 180 and -90 <= lat <= 90:
                        reconverted.append((lng, lat))
                coords = reconverted
                if len(coords) < 3:
                    self.add_error("coords_file", "Coordonnées invalides après conversion UTM.")
                    return None

            # Fermer le polygone
            if coords[0] != coords[-1]:
                coords.append(coords[0])

            poly = Polygon(coords, srid=4326)
            if not poly.valid:
                poly = poly.buffer(0)
                if not hasattr(poly, "geom_type") or poly.geom_type != "Polygon":
                    self.add_error("coords_file", "Les coordonnées ne forment pas un polygone valide.")
                    return None

            logger.info("Fichier coordonnées importé: %d sommets", len(coords) - 1)
            return poly

        except forms.ValidationError:
            raise
        except Exception as e:
            logger.error("Erreur parsing fichier coordonnées: %s", e, exc_info=True)
            self.add_error("coords_file", "Erreur lecture : {}".format(str(e)[:200]))
            return None

    # ─────────────────────────────────────────────────────────
    # Validation globale
    # ─────────────────────────────────────────────────────────
    def clean(self):
        cleaned = super().clean()

        # ── Unicité lot_number + ilot ──
        lot_number = cleaned.get("lot_number")
        ilot = cleaned.get("ilot")
        if lot_number and ilot:
            qs = Parcelle.objects.filter(lot_number=lot_number, ilot=ilot)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                existing = qs.first()
                self.add_error(
                    "lot_number",
                    f"Une parcelle avec le lot « {lot_number} » existe déjà "
                    f"dans l'îlot « {ilot} » (propriétaire : {existing.owner.get_full_name()})."
                )

        geom = cleaned.get("geometry_json")

        # Priorité 1 : geometry_json (dessin sur carte ou pré-rempli par JS)
        if geom:
            return cleaned

        # Priorité 2 : coordonnées textuelles (N sommets, WGS84 ou UTM)
        poly = self._build_polygon_from_coordinates_text()
        if poly:
            cleaned["geometry_json"] = poly
            return cleaned

        # Priorité 3 : Shapefile
        shp_geom, shp_attrs = self._parse_shapefile()
        if shp_geom:
            cleaned["geometry_json"] = shp_geom
            self._shp_attributes = shp_attrs
            return cleaned

        # Priorité 4 : DXF (AutoCAD)
        dxf_geom = self._parse_dxf()
        if dxf_geom:
            cleaned["geometry_json"] = dxf_geom
            return cleaned

        # Priorité 5 : Fichier TXT/CSV de coordonnées
        txt_geom = self._parse_coords_file()
        if txt_geom:
            cleaned["geometry_json"] = txt_geom
            return cleaned

        # Aucune géométrie fournie
        if not self.instance.pk or not self.instance.geometry:
            self.add_error(
                None,
                "Veuillez fournir une géométrie : dessinez sur la carte, "
                "saisissez les coordonnées, ou importez un fichier (Shapefile, DXF, TXT).",
            )

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        geom = self.cleaned_data.get("geometry_json")
        if geom:
            instance.geometry = geom

        # Auto-remplir depuis les attributs Shapefile
        shp_attrs = getattr(self, "_shp_attributes", {})
        if shp_attrs:
            field_mapping = {
                "title": ["TITRE", "TITLE", "NOM", "NAME", "LIBELLE", "LABEL"],
                "lot_number": ["LOT", "LOT_NUM", "NUMERO", "NUM_LOT", "LOT_NUMBER", "NUM"],
                "address": ["ADRESSE", "ADDRESS", "ADDR", "LIEU", "LOCALITE"],
                "description": ["DESC", "DESCRIPTION", "COMMENTAIRE", "COMMENT", "NOTES"],
            }
            for model_field, shp_keys in field_mapping.items():
                if not getattr(instance, model_field, None):
                    for key in shp_keys:
                        val = shp_attrs.get(key) or shp_attrs.get(key.lower())
                        if val:
                            setattr(instance, model_field, str(val))
                            break

            # Surface depuis attributs
            if not instance.surface_m2 or instance.surface_m2 == 0:
                for key in ["SURFACE", "SUPERFICIE", "AREA", "SURF_M2", "surface"]:
                    val = shp_attrs.get(key) or shp_attrs.get(key.lower())
                    if val:
                        try:
                            instance.surface_m2 = float(val)
                        except (ValueError, TypeError):
                            pass
                        break

        if commit:
            instance.save()
        return instance


class ParcelleMediaForm(forms.ModelForm):
    """Upload de médias pour une parcelle."""

    class Meta:
        model = ParcelleMedia
        fields = ["media_type", "title", "file"]
        widgets = {
            "media_type": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }


class ParcelleSearchForm(forms.Form):
    """Formulaire de recherche / filtrage des parcelles."""
    q = forms.CharField(required=False, widget=forms.TextInput(
        attrs={"class": "form-control", "placeholder": "Rechercher..."}
    ))
    zone = forms.ModelChoiceField(
        required=False,
        queryset=Zone.objects.all().order_by("name"),
        empty_label="Toutes les villes",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "Tous")] + list(Parcelle.Status.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    land_type = forms.ChoiceField(
        required=False,
        choices=[("", "Tous")] + list(Parcelle.LandType.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    price_min = forms.DecimalField(
        required=False, widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "Prix min"}
        ),
    )
    price_max = forms.DecimalField(
        required=False, widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "Prix max"}
        ),
    )
    surface_min = forms.DecimalField(
        required=False, widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "Surface min (m²)"}
        ),
    )
    surface_max = forms.DecimalField(
        required=False, widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "Surface max (m²)"}
        ),
    )


class BulkParcelleForm(forms.Form):
    """Formulaire d'import en lot de parcelles (CSV/Excel).

    Colonnes attendues :
    lot_number, title, description, land_type, surface_m2, price, address
    """
    file = forms.FileField(
        label="Fichier CSV ou Excel",
        help_text="Colonnes : lot_number, title, description, land_type, surface_m2, price, address",
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".csv,.xlsx,.xls"}),
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in (".csv", ".xlsx", ".xls"):
            raise ValidationError("Format non supporté. Utilisez un fichier CSV ou Excel (.xlsx).")
        if f.size > 5 * 1024 * 1024:  # 5 Mo max
            raise ValidationError("Le fichier ne doit pas dépasser 5 Mo.")
        return f
