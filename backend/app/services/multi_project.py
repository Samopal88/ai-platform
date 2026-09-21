"""
AI Workspace Platform - Multi-Project Service
Support for multiple projects with isolated storage

Each project has:
- docs/ - Documentation and progress
- state.json - Project state
- jobs/ - Job files
- history/ - Chat history
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


# Base storage path
STORAGE_ROOT = Path("/opt/ai-workspace/storage/projects")


@dataclass
class ProjectInfo:
    """Project information"""
    project_id: str
    name: str
    path: Path
    created_at: str
    updated_at: str
    description: str = ""


class MultiProjectManager:
    """
    Manages multiple projects with isolated storage.

    Each project lives in: storage/projects/{project_id}/
    """

    def __init__(self, storage_root: Optional[Path] = None):
        self.storage_root = storage_root or STORAGE_ROOT
        self._ensure_storage()

    def _ensure_storage(self):
        """Ensure storage root exists"""
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def _get_project_path(self, project_id: str) -> Path:
        """Get path to project directory"""
        return self.storage_root / project_id

    def _get_project_config_path(self, project_id: str) -> Path:
        """Get path to project config file"""
        return self._get_project_path(project_id) / "project.json"

    def _get_project_state_path(self, project_id: str) -> Path:
        """Get path to project state file"""
        return self._get_project_path(project_id) / "docs" / "progress" / "state.json"

    def create_project(
        self,
        project_id: str,
        name: str,
        description: str = ""
    ) -> ProjectInfo:
        """
        Create a new project with standard structure.

        Args:
            project_id: Unique project identifier
            name: Human-readable project name
            description: Project description

        Returns:
            ProjectInfo for the created project
        """
        project_path = self._get_project_path(project_id)

        if project_path.exists():
            raise ValueError(f"Project {project_id} already exists")

        # Create directory structure
        (project_path / "docs" / "progress").mkdir(parents=True)
        (project_path / "storage" / "jobs").mkdir(parents=True)
        (project_path / "storage" / "history").mkdir(parents=True)
        (project_path / "storage" / "files").mkdir(parents=True)

        now = datetime.now().isoformat()

        # Create project config
        config = {
            "project_id": project_id,
            "name": name,
            "description": description,
            "created_at": now,
            "updated_at": now,
            "settings": {
                "default_model": "claude-sonnet-4-20250514",
                "auto_save": True,
                "file_versioning": False
            }
        }
        config_path = self._get_project_config_path(project_id)
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))

        # Create initial state
        state = {
            "current_stage": "init",
            "active_task": None,
            "last_completed_task": None,
            "last_job_id": None,
            "last_changed_files": [],
            "updated_at": now,
            "mode": "self",
            "is_paused": False,
            "error": None,
            "history": []
        }
        state_path = self._get_project_state_path(project_id)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

        # Create initial CURRENT_STATUS.md
        status_content = f"""# CURRENT_STATUS
## {name}

---

## Current Stage
**Stage:** init
**Created:** {now[:10]}

---

## Already Completed
- [x] Project created

---

## Currently In Progress
- Nothing

---

## Blocked
- Nothing

---

## Next Steps
1. Define project goals
2. Start first task

---

## Files Changed
- None

---

## Last Updated
{now}

---

END OF DOCUMENT
"""
        status_path = project_path / "docs" / "progress" / "CURRENT_STATUS.md"
        status_path.write_text(status_content)

        return ProjectInfo(
            project_id=project_id,
            name=name,
            path=project_path,
            created_at=now,
            updated_at=now,
            description=description
        )

    def get_project(self, project_id: str) -> Optional[ProjectInfo]:
        """Get project info by ID"""
        config_path = self._get_project_config_path(project_id)

        if not config_path.exists():
            return None

        try:
            config = json.loads(config_path.read_text())
            return ProjectInfo(
                project_id=config["project_id"],
                name=config["name"],
                path=self._get_project_path(project_id),
                created_at=config["created_at"],
                updated_at=config["updated_at"],
                description=config.get("description", "")
            )
        except Exception:
            return None

    def list_projects(self) -> List[ProjectInfo]:
        """List all projects"""
        projects = []

        for item in self.storage_root.iterdir():
            if item.is_dir():
                info = self.get_project(item.name)
                if info:
                    projects.append(info)

        # Sort by updated_at descending
        projects.sort(key=lambda p: p.updated_at, reverse=True)
        return projects

    def delete_project(self, project_id: str) -> bool:
        """
        Delete a project and all its data.
        WARNING: This is irreversible!
        """
        project_path = self._get_project_path(project_id)

        if not project_path.exists():
            return False

        try:
            shutil.rmtree(project_path)
            return True
        except Exception:
            return False

    def get_project_state(self, project_id: str) -> Dict[str, Any]:
        """Get project state"""
        state_path = self._get_project_state_path(project_id)

        if state_path.exists():
            try:
                return json.loads(state_path.read_text())
            except Exception:
                pass

        return {}

    def update_project_state(self, project_id: str, updates: Dict[str, Any]) -> bool:
        """Update project state"""
        state_path = self._get_project_state_path(project_id)

        state = self.get_project_state(project_id)
        state.update(updates)
        state["updated_at"] = datetime.now().isoformat()

        try:
            state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
            return True
        except Exception:
            return False

    def get_project_jobs_path(self, project_id: str) -> Path:
        """Get path to project's jobs directory"""
        return self._get_project_path(project_id) / "storage" / "jobs"

    def get_project_files_path(self, project_id: str) -> Path:
        """Get path to project's files directory"""
        return self._get_project_path(project_id) / "storage" / "files"


# Global instance
_manager: Optional[MultiProjectManager] = None


def get_project_manager() -> MultiProjectManager:
    """Get or create project manager instance"""
    global _manager
    if _manager is None:
        _manager = MultiProjectManager()
    return _manager


# Convenience functions
def create_project(project_id: str, name: str, description: str = "") -> ProjectInfo:
    """Create a new project"""
    return get_project_manager().create_project(project_id, name, description)


def get_project(project_id: str) -> Optional[ProjectInfo]:
    """Get project by ID"""
    return get_project_manager().get_project(project_id)


def list_projects() -> List[ProjectInfo]:
    """List all projects"""
    return get_project_manager().list_projects()


def get_project_path(project_id: str) -> Optional[Path]:
    """Get project path by ID"""
    info = get_project(project_id)
    return info.path if info else None
