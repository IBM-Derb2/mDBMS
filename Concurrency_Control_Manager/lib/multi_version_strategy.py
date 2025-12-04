from typing import Any, Dict, Set, Union, List
from dataclasses import dataclass, field
from .strategy_interface import ConcurrencyStrategy, Response


@dataclass
class Version:
    """Stores data with creation and expiration timestamps."""

    data: Any
    created_ts: int
    expired_ts: int

    def __repr__(self):
        return f"Version(data={self.data}, created={self.created_ts}, expired={self.expired_ts})"


class MultiVersionStrategy(ConcurrencyStrategy):

    def __init__(self):
        self.version_store: Dict[str, List[Version]] = {}
        self.tx_manager_ref = None

    def set_transaction_manager(self, tx_manager):
        """Set reference to transaction manager for GC."""
        self.tx_manager_ref = tx_manager

    def _get_object_id(self, obj: Any) -> str:
        return str(obj)

    def log_object(self, obj: Any, transaction_id: int, action: str):
        obj_id = self._get_object_id(obj)
        action = action.strip().upper()
        tx_ts = transaction_id

        if action == "WRITE":
            new_version = Version(data=obj, created_ts=tx_ts, expired_ts=999999)
            if obj_id not in self.version_store:
                self.version_store[obj_id] = []

            versions = self.version_store[obj_id]

            # Expire old active version
            for v in reversed(versions):
                if v.expired_ts == 999999:
                    v.expired_ts = tx_ts
                    break

            # Add new version
            versions.append(new_version)

        elif action == "READ":
            pass  # MVCC: read doesn't need logging, validate_object finds the version

        else:
            raise ValueError(f"Unknown action {action}. Use 'read' or 'write'.")

    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        obj_id = self._get_object_id(obj)
        action = action.strip().upper()
        tx_ts = transaction_id

        if action == "READ":
            if obj_id not in self.version_store or len(self.version_store[obj_id]) == 0:
                return Response(allowed=True, transaction_id=transaction_id)

            versions = self.version_store[obj_id]

            # Find valid version: created_ts <= tx_ts AND expired_ts > tx_ts
            for version in reversed(versions):
                if version.created_ts <= tx_ts and version.expired_ts > tx_ts:
                    return Response(allowed=True, transaction_id=transaction_id)

            # Fallback: find last version before tx_ts
            for version in reversed(versions):
                if version.created_ts < tx_ts:
                    return Response(allowed=True, transaction_id=transaction_id)

            return Response(allowed=False, transaction_id=transaction_id)

        elif action == "WRITE":
            # First-committer-wins: check if newer version exists
            if obj_id in self.version_store:
                for version in self.version_store[obj_id]:
                    if tx_ts < version.created_ts:
                        return Response(allowed=False, transaction_id=transaction_id)

            return Response(allowed=True, transaction_id=transaction_id)

        else:
            raise ValueError(f"Unknown action '{action}'. Use 'read' or 'write'.")

    def end_transaction(self, transaction_id: int):
        self.garbage_collect_versions()

    def garbage_collect_versions(self):
        """Remove old versions that are no longer needed."""
        if not self.tx_manager_ref:
            return

        active_txs = self.tx_manager_ref.active_transactions
        if not active_txs:
            return

        oldest_active_ts = min(active_txs) if active_txs else 999999

        # Clean up old versions for each object
        for obj_id in list(self.version_store.keys()):
            versions = self.version_store[obj_id]

            # Keep only versions that are live or could be read by active transactions
            cleaned = [
                v
                for v in versions
                if v.expired_ts == 999999 or v.expired_ts >= oldest_active_ts
            ]

            if cleaned:
                self.version_store[obj_id] = cleaned
            else:
                del self.version_store[obj_id]

    def print_version_store(self):
        """Print all versions for debugging."""
        print("\n" + "=" * 60)
        print("MVCC VERSION STORE")
        print("=" * 60)
        if not self.version_store:
            print("(empty)")
        else:
            for obj_id, versions in self.version_store.items():
                print(f"\nObject '{obj_id}': {len(versions)} version(s)")
                for i, version in enumerate(versions, 1):
                    status = "LIVE" if version.expired_ts == 999999 else "EXPIRED"
                    print(
                        f"  {i}. {status} - Created: TS{version.created_ts}, "
                        f"Expired: {'INF' if version.expired_ts == 999999 else f'TS{version.expired_ts}'}"
                    )
        print("=" * 60 + "\n")

    def get_statistics(self) -> Dict[str, Any]:
        """Get MVCC statistics."""
        total_objects = len(self.version_store)
        total_versions = sum(len(versions) for versions in self.version_store.values())
        live_versions = sum(
            sum(1 for v in versions if v.expired_ts == 999999)
            for versions in self.version_store.values()
        )
        expired_versions = total_versions - live_versions

        avg_versions_per_object = (
            total_versions / total_objects if total_objects > 0 else 0
        )

        return {
            "total_objects": total_objects,
            "total_versions": total_versions,
            "live_versions": live_versions,
            "expired_versions": expired_versions,
            "avg_versions_per_object": avg_versions_per_object,
        }
