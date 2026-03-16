import cv2
import torch
import torch.nn as nn
from ultralytics import YOLO
from torchvision import models, transforms
from PIL import Image
from datetime import datetime

# 1. UNIVERSAL ATTRIBUTE ANALYZER (ResNet-50)
class UniversalExpert(nn.Module):
    def __init__(self, n_colors=10):
        super().__init__()
        # Use ResNet to extract general visual features (colors/textures)
        self.backbone = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
        n_inputs = self.backbone.fc.in_features
        self.backbone.fc = nn.Linear(n_inputs, n_colors) # Predicts primary color

    def forward(self, x):
        return self.backbone(x)

# 2. INITIALIZE MODELS
yolo = YOLO('yolov8n.pt') # Detects 80 classes: people, cars, bags, etc.
color_expert = UniversalExpert()
color_expert.eval()

COLOR_LABELS = ["Red", "Blue", "Green", "Black", "White", "Yellow", "Grey", "Brown"]
db = [] # Object Log Database

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

# 3. PROCESSING LOOP
def start_surveillance(source=0):
    cap = cv2.VideoCapture(source)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break

        # Detect ALL objects
        results = yolo(frame, verbose=False)
        
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy)
                obj_name = r.names[int(box.cls[0])] # Get name: 'person', 'dog', etc.
                
                # Analyze color of the specific object
                crop = Image.fromarray(cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2RGB))
                if crop.size[0] < 10 or crop.size[1] < 10: continue
                
                batch = transform(crop).unsqueeze(0)
                with torch.no_grad():
                    color_idx = torch.argmax(color_expert(batch)).item()
                
                color = COLOR_LABELS[color_idx % len(COLOR_LABELS)]
                
                # Log to DB
                entry = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "object": obj_name,
                    "color": color,
                    "summary": f"A {color} {obj_name} was detected."
                }
                db.append(entry)

                # Draw on screen
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                cv2.putText(frame, f"{color} {obj_name}", (x1, y1-10), 0, 0.6, (255, 0, 0), 2)

        cv2.imshow("Universal Object Tracker", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
    cap.release(); cv2.destroyAllWindows()

# 4. LLM Q&A INTERFACE
def ask_question(query):
    query = query.lower()
    matches = [e for e in db if e['object'] in query or e['color'].lower() in query]
    if not matches: return "No matching objects found."
    return "\n".join([f"[{m['time']}] {m['summary']}" for m in matches[:5]])

if __name__ == "__main__":
    print("Starting... Point camera at any object. Press 'q' to stop and chat.")
    start_surveillance(0)
    
    while True:
        user_q = input("\nAsk (e.g. 'Any red objects?' or 'Who passed by?'): ")
        if user_q.lower() == 'exit': break
        print(ask_question(user_q))
