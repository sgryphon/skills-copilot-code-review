"""
Announcements Router

Provides API endpoints for managing and viewing announcements.
Only authenticated users can manage announcements.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date
from bson import ObjectId
from ..database import announcements_collection

router = APIRouter(prefix="/announcements", tags=["announcements"])


class AnnouncementCreate(BaseModel):
    """Model for creating a new announcement"""
    message: str = Field(..., min_length=1, max_length=500, description="The announcement message")
    start_date: Optional[str] = Field(None, description="Optional start date (YYYY-MM-DD)")
    expiration_date: str = Field(..., description="Required expiration date (YYYY-MM-DD)")


class AnnouncementUpdate(BaseModel):
    """Model for updating an announcement"""
    message: Optional[str] = Field(None, min_length=1, max_length=500, description="The announcement message")
    start_date: Optional[str] = Field(None, description="Optional start date (YYYY-MM-DD)")
    expiration_date: Optional[str] = Field(None, description="Required expiration date (YYYY-MM-DD)")


@router.get("/active")
async def get_active_announcements():
    """
    Get all currently active announcements.
    
    An announcement is active if:
    - Current date is after or equal to start_date (if start_date is set)
    - Current date is before expiration_date
    
    Returns a list of active announcements ordered by creation date.
    """
    try:
        today = date.today().isoformat()
        
        # Find announcements that are currently active
        query = {
            "$and": [
                {"expiration_date": {"$gt": today}},
                {"$or": [
                    {"start_date": {"$exists": False}},
                    {"start_date": None},
                    {"start_date": {"$lte": today}}
                ]}
            ]
        }
        
        announcements = list(announcements_collection.find(query))
        
        # Convert ObjectId to string for JSON serialization
        for announcement in announcements:
            announcement["id"] = str(announcement["_id"])
            del announcement["_id"]
        
        return {"announcements": announcements}
    except Exception as e:
        print(f"Error fetching active announcements: {e}")
        return {"announcements": []}


@router.get("/all")
async def get_all_announcements(username: str = Query(..., description="Username for authentication")):
    """
    Get all announcements (active and inactive).
    
    Requires authentication - username must be provided.
    Used for the management interface.
    
    Returns all announcements ordered by expiration date (descending).
    """
    try:
        # Verify user is authenticated (basic check - in production, use proper auth)
        if not username:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        announcements = list(announcements_collection.find().sort("expiration_date", -1))
        
        # Convert ObjectId to string for JSON serialization
        for announcement in announcements:
            announcement["id"] = str(announcement["_id"])
            del announcement["_id"]
        
        return {"announcements": announcements}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching all announcements: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch announcements")


@router.post("/")
async def create_announcement(
    announcement: AnnouncementCreate,
    username: str = Query(..., description="Username for authentication")
):
    """
    Create a new announcement.
    
    Requires authentication - username must be provided.
    
    Returns the created announcement with its ID.
    """
    try:
        # Verify user is authenticated
        if not username:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Validate dates
        try:
            expiration = datetime.strptime(announcement.expiration_date, "%Y-%m-%d").date()
            if announcement.start_date:
                start = datetime.strptime(announcement.start_date, "%Y-%m-%d").date()
                if start > expiration:
                    raise HTTPException(status_code=400, detail="Start date must be before expiration date")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Create announcement document
        announcement_doc = {
            "message": announcement.message,
            "start_date": announcement.start_date,
            "expiration_date": announcement.expiration_date,
            "created_at": datetime.now().isoformat(),
            "created_by": username
        }
        
        result = announcements_collection.insert_one(announcement_doc)
        
        # Return created announcement
        announcement_doc["id"] = str(result.inserted_id)
        if "_id" in announcement_doc:
            del announcement_doc["_id"]
        
        return announcement_doc
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating announcement: {e}")
        raise HTTPException(status_code=500, detail="Failed to create announcement")


@router.put("/{announcement_id}")
async def update_announcement(
    announcement_id: str,
    announcement: AnnouncementUpdate,
    username: str = Query(..., description="Username for authentication")
):
    """
    Update an existing announcement.
    
    Requires authentication - username must be provided.
    
    Returns the updated announcement.
    """
    try:
        # Verify user is authenticated
        if not username:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Validate ObjectId
        try:
            obj_id = ObjectId(announcement_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid announcement ID")
        
        # Build update document
        update_doc = {}
        if announcement.message is not None:
            update_doc["message"] = announcement.message
        if announcement.start_date is not None:
            update_doc["start_date"] = announcement.start_date
        if announcement.expiration_date is not None:
            update_doc["expiration_date"] = announcement.expiration_date
        
        if not update_doc:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Validate dates if both are present
        if "start_date" in update_doc or "expiration_date" in update_doc:
            existing = announcements_collection.find_one({"_id": obj_id})
            if not existing:
                raise HTTPException(status_code=404, detail="Announcement not found")
            
            exp_date = update_doc.get("expiration_date", existing.get("expiration_date"))
            start_date = update_doc.get("start_date", existing.get("start_date"))
            
            if start_date and exp_date:
                try:
                    start = datetime.strptime(start_date, "%Y-%m-%d").date()
                    exp = datetime.strptime(exp_date, "%Y-%m-%d").date()
                    if start > exp:
                        raise HTTPException(status_code=400, detail="Start date must be before expiration date")
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        update_doc["updated_at"] = datetime.now().isoformat()
        update_doc["updated_by"] = username
        
        # Update announcement
        result = announcements_collection.update_one(
            {"_id": obj_id},
            {"$set": update_doc}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        # Return updated announcement
        updated = announcements_collection.find_one({"_id": obj_id})
        updated["id"] = str(updated["_id"])
        del updated["_id"]
        
        return updated
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating announcement: {e}")
        raise HTTPException(status_code=500, detail="Failed to update announcement")


@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: str,
    username: str = Query(..., description="Username for authentication")
):
    """
    Delete an announcement.
    
    Requires authentication - username must be provided.
    
    Returns success message.
    """
    try:
        # Verify user is authenticated
        if not username:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Validate ObjectId
        try:
            obj_id = ObjectId(announcement_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid announcement ID")
        
        # Delete announcement
        result = announcements_collection.delete_one({"_id": obj_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        return {"message": "Announcement deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting announcement: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete announcement")
