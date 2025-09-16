import clr
clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')

from System.Windows.Forms import Form, Label, TextBox, Button, DialogResult, FormStartPosition
from System.Drawing import Point, Size

CABLE_TYPES = [

]

class InputBox(Form):
    def __init__(self, title="Kabel Hinzufügen", prompt="Kabel-Nummer eingeben"):
        self.Text = title
        self.Width = 300
        self.Height = 150
        self.StartPosition = FormStartPosition.CenterParent
        self.ShowIcon = False

        self.label = Label()
        self.label.Text = prompt
        self.label.Location = Point(10, 10)
        self.label.Size = Size(260, 20)
        self.Controls.Add(self.label)

        self.textbox = TextBox()
        self.textbox.Location = Point(10, 40)
        self.textbox.Size = Size(260, 20)
        self.Controls.Add(self.textbox)

        self.ok_button = Button()
        self.ok_button.Text = "OK"
        self.ok_button.Location = Point(110, 70)
        self.ok_button.DialogResult = DialogResult.OK
        self.AcceptButton = self.ok_button
        self.Controls.Add(self.ok_button)

        self.CancelButton = self.ok_button

def show_input_box(prompt="Enter value:", title="Input"):
    form = InputBox(prompt, title)
    result = form.ShowDialog()
    if result == DialogResult.OK:
        return form.textbox.Text
    else:
        return None

# Example usage
if __name__ == "__main__":
    user_input = show_input_box("What is your name?", "Name Input")
    if user_input:
        print("User entered:", user_input)
    else:
        print("User cancelled input.")
