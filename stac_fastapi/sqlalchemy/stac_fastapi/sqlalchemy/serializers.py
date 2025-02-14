"""Serializers."""
import abc
import json
from datetime import datetime
from typing import TypedDict

import attr
import geoalchemy2 as ga
from stac_pydantic.shared import DATETIME_RFC339

from stac_fastapi.sqlalchemy.models import database
from stac_fastapi.types import stac as stac_types
from stac_fastapi.types.config import Settings
from stac_fastapi.types.links import CollectionLinks, ItemLinks, resolve_links


@attr.s  # type:ignore
class Serializer(abc.ABC):
    """Defines serialization methods between the API and the data model."""

    @classmethod
    @abc.abstractmethod
    def db_to_stac(cls, db_model: database.BaseModel, base_url: str) -> TypedDict:
        """Transform database model to stac."""
        ...

    @classmethod
    @abc.abstractmethod
    def stac_to_db(
        cls, stac_data: TypedDict, exclude_geometry: bool = False
    ) -> database.BaseModel:
        """Transform stac to database model."""
        ...

    @classmethod
    def row_to_dict(cls, db_model: database.BaseModel):
        """Transform a database model to it's dictionary representation."""
        d = {}
        for column in db_model.__table__.columns:
            value = getattr(db_model, column.name)
            if value:
                d[column.name] = value
        return d


class ItemSerializer(Serializer):
    """Serialization methods for STAC items."""

    @classmethod
    def db_to_stac(cls, db_model: database.Item, base_url: str) -> stac_types.Item:
        """Transform database model to stac item."""
        properties = db_model.properties.copy()
        indexed_fields = Settings.get().indexed_fields
        for field in indexed_fields:
            # Use getattr to accommodate extension namespaces
            field_value = getattr(db_model, field.split(":")[-1])
            if field == "datetime":
                field_value = field_value.strftime(DATETIME_RFC339)
            properties[field] = field_value
        item_id = db_model.id
        collection_id = db_model.collection_id
        item_links = ItemLinks(
            collection_id=collection_id, item_id=item_id, base_url=base_url
        ).create_links()

        db_links = db_model.links
        if db_links:
            item_links += resolve_links(db_links, base_url)

        stac_extensions = db_model.stac_extensions or []

        # The custom geometry we are using emits geojson if the geometry is bound to the database
        # Otherwise it will return a geoalchemy2 WKBElement
        # TODO: It's probably best to just remove the custom geometry type
        geometry = db_model.geometry
        if isinstance(geometry, ga.elements.WKBElement):
            geometry = ga.shape.to_shape(geometry).__geo_interface__
        if isinstance(geometry, str):
            geometry = json.loads(geometry)

        return stac_types.Item(
            type="Feature",
            stac_version=db_model.stac_version,
            stac_extensions=stac_extensions,
            id=db_model.id,
            collection=db_model.collection_id,
            geometry=geometry,
            bbox=[float(x) for x in db_model.bbox],
            properties=properties,
            links=item_links,
            assets=db_model.assets,
        )

    @classmethod
    def stac_to_db(
        cls, stac_data: TypedDict, exclude_geometry: bool = False
    ) -> database.Item:
        """Transform stac item to database model."""
        indexed_fields = {}
        for field in Settings.get().indexed_fields:
            # Use getattr to accommodate extension namespaces
            field_value = stac_data["properties"][field]
            if field == "datetime":
                field_value = datetime.strptime(field_value, DATETIME_RFC339)
            indexed_fields[field.split(":")[-1]] = field_value

            # TODO: Exclude indexed fields from the properties jsonb field to prevent duplication

            now = datetime.utcnow().strftime(DATETIME_RFC339)
            if "created" not in stac_data["properties"]:
                stac_data["properties"]["created"] = now
            stac_data["properties"]["updated"] = now

        return database.Item(
            id=stac_data["id"],
            collection_id=stac_data["collection"],
            stac_version=stac_data["stac_version"],
            stac_extensions=stac_data.get("stac_extensions"),
            geometry=json.dumps(stac_data["geometry"]),
            bbox=stac_data["bbox"],
            properties=stac_data["properties"],
            assets=stac_data["assets"],
            **indexed_fields,
        )


class CollectionSerializer(Serializer):
    """Serialization methods for STAC collections."""

    @classmethod
    def db_to_stac(cls, db_model: database.Collection, base_url: str) -> TypedDict:
        """Transform database model to stac collection."""
        collection_links = CollectionLinks(
            collection_id=db_model.id, base_url=base_url
        ).create_links()

        db_links = db_model.links
        if db_links:
            collection_links += resolve_links(db_links, base_url)

        stac_extensions = db_model.stac_extensions or []

        return stac_types.Collection(
            type="Collection",
            id=db_model.id,
            stac_extensions=stac_extensions,
            stac_version=db_model.stac_version,
            title=db_model.title,
            description=db_model.description,
            keywords=db_model.keywords,
            license=db_model.license,
            providers=db_model.providers,
            summaries=db_model.summaries,
            extent=db_model.extent,
            links=collection_links,
        )

    @classmethod
    def stac_to_db(
        cls, stac_data: TypedDict, exclude_geometry: bool = False
    ) -> database.Collection:
        """Transform stac collection to database model."""
        return database.Collection(**dict(stac_data))
