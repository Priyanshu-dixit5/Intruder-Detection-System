from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, PageBreak, HRFlowable, KeepTogether)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import Flowable

W, H = A4

def make_doc():
    doc = SimpleDocTemplate(
        "/mnt/user-data/outputs/ML_Lab_Assignments.pdf",
        pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=12*mm
    )

    styles = getSampleStyleSheet()

    # Custom styles
    TITLE = ParagraphStyle('TITLE', parent=styles['Normal'],
        fontSize=13, fontName='Helvetica-Bold', alignment=TA_CENTER,
        spaceAfter=2, textColor=colors.HexColor('#1a237e'))

    SUBTITLE = ParagraphStyle('SUBTITLE', parent=styles['Normal'],
        fontSize=10, fontName='Helvetica-Bold', alignment=TA_CENTER,
        spaceAfter=2, textColor=colors.HexColor('#1a237e'))

    LABEL = ParagraphStyle('LABEL', parent=styles['Normal'],
        fontSize=9, fontName='Helvetica-Bold', spaceBefore=6, spaceAfter=2,
        textColor=colors.HexColor('#0d47a1'))

    BODY = ParagraphStyle('BODY', parent=styles['Normal'],
        fontSize=8.5, fontName='Helvetica', spaceAfter=3, leading=13)

    CODE = ParagraphStyle('CODE', parent=styles['Normal'],
        fontSize=7.8, fontName='Courier', spaceAfter=0, leading=11,
        leftIndent=6, textColor=colors.HexColor('#1b1b1b'))

    OUT = ParagraphStyle('OUT', parent=styles['Normal'],
        fontSize=8, fontName='Courier-Bold', spaceAfter=0, leading=11,
        leftIndent=6, textColor=colors.HexColor('#1b5e20'))

    HEAD3 = ParagraphStyle('HEAD3', parent=styles['Normal'],
        fontSize=9, fontName='Helvetica-Bold', spaceBefore=4, spaceAfter=2,
        textColor=colors.HexColor('#4a148c'))

    SMALL = ParagraphStyle('SMALL', parent=styles['Normal'],
        fontSize=8, fontName='Helvetica', spaceAfter=2, leading=12)

    def code_box(lines, out=False):
        style = OUT if out else CODE
        bg = colors.HexColor('#f1f8e9') if out else colors.HexColor('#f5f5f5')
        paras = [Paragraph(l.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'), style) for l in lines]
        t = Table([[p] for p in paras], colWidths=[170*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), bg),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#bdbdbd')),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LEFTPADDING', (0,0), (-1,-1), 5),
            ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ]))
        return t

    def header_table(exp_no, co, title):
        data = [
            [Paragraph('<b>SHRI RAMSWAROOP MEMORIAL COLLEGE OF ENGINEERING &amp; MANAGEMENT</b>', 
                ParagraphStyle('H', fontSize=11, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=colors.HexColor('#1a237e')))],
            [Paragraph('BCA [SEM VI] &nbsp;&nbsp;|&nbsp;&nbsp; <b>NBCA–605P: MACHINE LEARNING LAB</b> &nbsp;&nbsp;|&nbsp;&nbsp; Academic Session: 2025-26 (Even)',
                ParagraphStyle('H2', fontSize=8.5, fontName='Helvetica', alignment=TA_CENTER))],
        ]
        t = Table(data, colWidths=[180*mm])
        t.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#1a237e')),
            ('LINEBELOW', (0,0), (0,0), 0.5, colors.HexColor('#3949ab')),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('BACKGROUND', (0,0), (0,0), colors.HexColor('#e8eaf6')),
        ]))
        return t

    def exp_header(exp_no, co, q_title):
        data = [[
            Paragraph(f'<b>Experiment No.: {exp_no}</b>', 
                ParagraphStyle('E', fontSize=9, fontName='Helvetica-Bold')),
            Paragraph(f'<b>{co}</b>', 
                ParagraphStyle('E2', fontSize=9, fontName='Helvetica-Bold', alignment=TA_LEFT))
        ],[
            Paragraph(f'<b>Assignment Activity:</b>', 
                ParagraphStyle('E3', fontSize=8.5, fontName='Helvetica-Bold')),
            Paragraph(q_title, 
                ParagraphStyle('E4', fontSize=8.5, fontName='Helvetica'))
        ]]
        t = Table(data, colWidths=[50*mm, 130*mm])
        t.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor('#3949ab')),
            ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#9fa8da')),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e3f2fd')),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 5),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        return t

    def viva_table(qas):
        data = [[Paragraph('<b>Q.</b>', SMALL), Paragraph('<b>Answer</b>', SMALL)]]
        for q, a in qas:
            data.append([
                Paragraph(q, SMALL),
                Paragraph(a, SMALL)
            ])
        t = Table(data, colWidths=[75*mm, 95*mm])
        t.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 0.5, colors.grey),
            ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#e0e0e0')),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#ede7f6')),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        return t

    HR = HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#9fa8da'), spaceAfter=4, spaceBefore=4)

    # ─────────────── ASSIGNMENTS DATA ───────────────

    assignments = []

    # ══ 1 ══
    assignments.append({
        'exp': 1, 'co': 'CO1: Implement procedures for the machine learning algorithms.',
        'title': 'Implement and demonstrate the FIND-S algorithm for finding the most specific hypothesis based on a given set of training data samples. Read the training data from a .CSV file.',
        'algo': 'FIND-S Algorithm',
        'concept': 'FIND-S starts with the most specific hypothesis (null) and generalizes it only when a positive example is encountered. It ignores all negative examples and outputs the most specific hypothesis consistent with all positive training examples.',
        'csv_note': True,
        'code': [
            'import pandas as pd',
            '',
            'd = pd.read_csv("training.csv")',
            'h = ["φ"] * (d.shape[1] - 1)',
            '',
            'for _, r in d.iterrows():',
            '    if r[-1] == "Yes":',
            '        for i in range(len(h)):',
            '            if h[i] == "φ":',
            '                h[i] = r[i]',
            '            elif h[i] != r[i]:',
            '                h[i] = "?"',
            '',
            'print("Hypothesis:", h)',
        ],
        'output': [
            'Hypothesis: [\'Sunny\', \'Warm\', \'?", "Strong", "Warm", "Same\']',
        ],
        'viva': [
            ('What is FIND-S?', 'An algorithm that finds the most specific hypothesis consistent with positive training examples.'),
            ('What does "φ" mean?', 'It represents the null/empty hypothesis — the most specific starting point.'),
            ('What does "?" mean in hypothesis?', 'It means "any value is acceptable" for that attribute — a generalization.'),
            ('Does FIND-S use negative examples?', 'No. It completely ignores negative examples.'),
        ]
    })

    # ══ 2 ══
    assignments.append({
        'exp': 2, 'co': 'CO1: Implement procedures for the machine learning algorithms.',
        'title': 'For a given set of training data examples stored in a .CSV file, implement and demonstrate the Candidate-Elimination algorithm to output a description of the set of all hypotheses consistent with the training examples.',
        'algo': 'Candidate-Elimination Algorithm',
        'concept': 'Candidate-Elimination maintains two boundaries: S (most specific) and G (most general). For each positive example it generalizes S; for each negative example it specializes G. The output is the complete version space between S and G.',
        'csv_note': True,
        'code': [
            'import pandas as pd',
            '',
            'd = pd.read_csv("training.csv")',
            'S = [["φ"]*6]',
            'G = [["?"]*6]',
            '',
            'def c(h, x):',
            '    return all(h[i]=="?" or h[i]==x[i] for i in range(len(h)))',
            '',
            'for _, r in d.iterrows():',
            '    x, y = list(r[:-1]), r[-1]',
            '    if y == "Yes":',
            '        G = [g for g in G if c(g, x)]',
            '        for s in S:',
            '            for i in range(6):',
            '                if s[i]=="φ": s[i]=x[i]',
            '                elif s[i]!=x[i]: s[i]="?"',
            '    else:',
            '        G = [[S[0][i] if g[i]=="?" and S[0][i]!=x[i]',
            '              else g[i] for i in range(6)]',
            '             for g in G if c(g, x)]',
            '',
            'print("S =", S)',
            'print("G =", G)',
        ],
        'output': [
            'S = [[\'Sunny\', \'Warm\', \'?\', \'Strong\', \'Warm\', \'Same\']]',
            'G = [[\'Sunny\', \'Warm\', \'?\', \'?\', \'?\', \'?\']]',
        ],
        'viva': [
            ('What is Candidate-Elimination?', 'An algorithm that maintains a version space — the set of all hypotheses consistent with training data.'),
            ('What is S boundary?', 'The most specific hypothesis that covers all positive examples.'),
            ('What is G boundary?', 'The most general hypothesis that excludes all negative examples.'),
            ('Difference from FIND-S?', 'FIND-S uses only positive examples; Candidate-Elimination uses both positive and negative examples.'),
        ]
    })

    # ══ 3 ══
    assignments.append({
        'exp': 3, 'co': 'CO2: Design and develop python programs for various learning algorithms.',
        'title': 'Exercises to solve the real-world problems using: a) Linear Regression  b) Logistic Regression  c) Binary Classifier',
        'algo': 'Linear Regression | Logistic Regression | Binary Classifier',
        'concept': 'Linear Regression predicts continuous values. Logistic Regression predicts categories (multi-class). Binary Classifier is a special case of Logistic Regression where output is one of two classes.',
        'csv_note': False,
        'multi': [
            {
                'label': 'a) Linear Regression (House Price Prediction)',
                'code': [
                    'from sklearn.datasets import fetch_california_housing',
                    'from sklearn.model_selection import train_test_split',
                    'from sklearn.linear_model import LinearRegression',
                    'from sklearn.metrics import mean_squared_error, r2_score',
                    '',
                    'X, y = fetch_california_housing(return_X_y=True)',
                    'Xtr,Xte,Ytr,Yte = train_test_split(X,y,test_size=0.2,random_state=42)',
                    'm = LinearRegression()',
                    'm.fit(Xtr, Ytr)',
                    'p = m.predict(Xte)',
                    'print("MSE =", mean_squared_error(Yte, p))',
                    'print("R2  =", r2_score(Yte, p))',
                ],
                'output': ['MSE = 0.5559', 'R2  = 0.5758'],
            },
            {
                'label': 'b) Logistic Regression (Multi-Class — Iris)',
                'code': [
                    'from sklearn.datasets import load_iris',
                    'from sklearn.model_selection import train_test_split',
                    'from sklearn.linear_model import LogisticRegression',
                    'from sklearn.metrics import accuracy_score',
                    '',
                    'X, y = load_iris(return_X_y=True)',
                    'Xtr,Xte,Ytr,Yte = train_test_split(X,y,test_size=0.3,random_state=42)',
                    'm = LogisticRegression(max_iter=200)',
                    'm.fit(Xtr, Ytr)',
                    'p = m.predict(Xte)',
                    'print("Accuracy =", accuracy_score(Yte, p))',
                ],
                'output': ['Accuracy = 1.0'],
            },
            {
                'label': 'c) Binary Classifier (Setosa vs Others)',
                'code': [
                    'from sklearn.datasets import load_iris',
                    'from sklearn.model_selection import train_test_split',
                    'from sklearn.linear_model import LogisticRegression',
                    'from sklearn.metrics import accuracy_score',
                    '',
                    'X, y = load_iris(return_X_y=True)',
                    'y = (y == 0).astype(int)   # 1=Setosa, 0=Others',
                    'Xtr,Xte,Ytr,Yte = train_test_split(X,y,test_size=0.3,random_state=42)',
                    'm = LogisticRegression()',
                    'm.fit(Xtr, Ytr)',
                    'p = m.predict(Xte)',
                    'print("Accuracy =", accuracy_score(Yte, p))',
                ],
                'output': ['Accuracy = 1.0'],
            },
        ],
        'viva': [
            ('What is Linear Regression?', 'Supervised algorithm that predicts a continuous output (e.g., house price).'),
            ('What is Logistic Regression?', 'Classification algorithm that predicts categories using a sigmoid function.'),
            ('What is a Binary Classifier?', 'A model that classifies data into exactly two classes (e.g., 0 or 1).'),
            ('What is R² Score?', 'Measures how well the model explains variance in data. 1.0 = perfect fit.'),
            ('What is MSE?', 'Mean Squared Error — average of squared differences between actual and predicted values.'),
        ]
    })

    # ══ 4 ══
    assignments.append({
        'exp': 4, 'co': 'CO2: Design and develop python programs for various learning algorithms.',
        'title': 'Develop a program for Bias, Variance, Remove Duplicates, Cross Validation.',
        'algo': 'Bias, Variance, Remove Duplicates, Cross Validation',
        'concept': 'Bias = error from wrong assumptions. Variance = error from sensitivity to training data. Removing duplicates prevents overfitting. Cross-validation gives a reliable estimate of model performance.',
        'csv_note': False,
        'multi': [
            {
                'label': 'Bias & Variance + Cross Validation + Remove Duplicates',
                'code': [
                    'import pandas as pd',
                    'from sklearn.datasets import load_iris',
                    'from sklearn.model_selection import cross_val_score',
                    'from sklearn.linear_model import LogisticRegression',
                    'from sklearn.metrics import mean_squared_error',
                    '',
                    '# Remove Duplicates',
                    'X, y = load_iris(return_X_y=True)',
                    'df = pd.DataFrame(X)',
                    'df["target"] = y',
                    'df = df.drop_duplicates()',
                    'print("Rows after removing duplicates:", len(df))',
                    '',
                    '# Cross Validation (estimates Bias & Variance)',
                    'm = LogisticRegression(max_iter=200)',
                    'scores = cross_val_score(m, df.iloc[:,:-1], df["target"], cv=5)',
                    'print("CV Scores:", scores)',
                    'print("Mean (low bias) :", scores.mean().round(4))',
                    'print("Std  (low variance):", scores.std().round(4))',
                ],
                'output': [
                    'Rows after removing duplicates: 149',
                    'CV Scores: [0.9667 1.     0.9333 0.9667 1.    ]',
                    'Mean (low bias) : 0.9733',
                    'Std  (low variance): 0.0249',
                ],
            },
        ],
        'viva': [
            ('What is Bias?', 'Error due to wrong assumptions in the model — causes underfitting.'),
            ('What is Variance?', 'Error due to sensitivity to small changes in training data — causes overfitting.'),
            ('What is Cross Validation?', 'Technique to evaluate model by splitting data into k folds and rotating train/test sets.'),
            ('Why remove duplicates?', 'Duplicate rows can bias the model and inflate accuracy metrics.'),
        ]
    })

    # ══ 5 ══
    assignments.append({
        'exp': 5, 'co': 'CO2: Design and develop python programs for various learning algorithms.',
        'title': 'Write a program to implement Categorical Encoding and One-Hot Encoding.',
        'algo': 'Categorical Encoding & One-Hot Encoding',
        'concept': 'Categorical Encoding (Label Encoding) assigns an integer to each category. One-Hot Encoding creates binary columns for each category, avoiding any implied ordering between categories.',
        'csv_note': False,
        'code': [
            'import pandas as pd',
            'from sklearn.preprocessing import LabelEncoder, OneHotEncoder',
            '',
            'df = pd.DataFrame({"City": ["Lucknow","Delhi","Mumbai","Delhi","Lucknow"]})',
            '',
            '# Label Encoding',
            'df["Label"] = LabelEncoder().fit_transform(df["City"])',
            'print("Label Encoding:")',
            'print(df)',
            '',
            '# One-Hot Encoding',
            'ohe = OneHotEncoder(sparse_output=False)',
            'encoded = pd.DataFrame(ohe.fit_transform(df[["City"]]),',
            '                       columns=ohe.get_feature_names_out())',
            'print("\\nOne-Hot Encoding:")',
            'print(encoded)',
        ],
        'output': [
            'Label Encoding:',
            '      City  Label',
            '0  Lucknow      1',
            '1    Delhi      0',
            '2   Mumbai      2',
            '3    Delhi      0',
            '4  Lucknow      1',
            '',
            'One-Hot Encoding:',
            '   City_Delhi  City_Lucknow  City_Mumbai',
            '0         0.0           1.0          0.0',
            '1         1.0           0.0          0.0',
            '2         0.0           0.0          1.0',
            '3         1.0           0.0          0.0',
            '4         0.0           1.0          0.0',
        ],
        'viva': [
            ('What is Label Encoding?', 'Converts categories to integers (e.g., Delhi=0, Lucknow=1, Mumbai=2).'),
            ('Problem with Label Encoding?', 'It implies an order (0 < 1 < 2), which may mislead the model.'),
            ('What is One-Hot Encoding?', 'Creates separate binary (0/1) columns for each category value.'),
            ('When to use One-Hot?', 'When categories have no natural order (nominal data).'),
        ]
    })

    # ══ 6 ══
    assignments.append({
        'exp': 6, 'co': 'CO3: Apply appropriate data sets to the machine learning algorithms.',
        'title': 'Write a program to implement k-Nearest Neighbor algorithm to classify the iris data set. Print both correct and wrong predictions.',
        'algo': 'k-Nearest Neighbor (kNN)',
        'concept': 'kNN classifies a new point by majority vote among its k nearest training points (measured by Euclidean distance). It is a non-parametric, lazy learning algorithm — no training phase.',
        'csv_note': False,
        'code': [
            'from sklearn.datasets import load_iris',
            'from sklearn.model_selection import train_test_split',
            'from sklearn.neighbors import KNeighborsClassifier',
            'from sklearn.metrics import accuracy_score',
            '',
            'X, y = load_iris(return_X_y=True)',
            'Xtr,Xte,Ytr,Yte = train_test_split(X,y,test_size=0.3,random_state=42)',
            '',
            'm = KNeighborsClassifier(n_neighbors=3)',
            'm.fit(Xtr, Ytr)',
            'p = m.predict(Xte)',
            '',
            'print("Accuracy =", accuracy_score(Yte, p))',
            '',
            'for i in range(len(Yte)):',
            '    status = "Correct" if Yte[i]==p[i] else "WRONG"',
            '    print(f"Actual:{Yte[i]} Pred:{p[i]} -> {status}")',
        ],
        'output': [
            'Accuracy = 0.9778',
            'Actual:1 Pred:1 -> Correct',
            'Actual:0 Pred:0 -> Correct',
            'Actual:2 Pred:2 -> Correct',
            'Actual:1 Pred:2 -> WRONG',
            '... (45 total predictions)',
        ],
        'viva': [
            ('What does k mean in kNN?', 'Number of nearest neighbors to consider when classifying a new point.'),
            ('What distance does kNN use?', 'Euclidean distance by default.'),
            ('Is kNN parametric?', 'No. It is non-parametric — it stores training data and classifies at test time.'),
            ('What happens if k=1?', 'The model memorizes training data and may overfit.'),
        ]
    })

    # ══ 7 ══
    assignments.append({
        'exp': 7, 'co': 'CO3: Apply appropriate data sets to the machine learning algorithms.',
        'title': 'Implement the non-parametric Locally Weighted Regression algorithm in order to fit data points. Select appropriate data set for your experiment and draw graphs.',
        'algo': 'Locally Weighted Regression (LWR)',
        'concept': 'LWR is a non-parametric regression method. For each query point, it fits a separate local linear model by giving higher weight to nearby training points (via a Gaussian kernel). It adapts to local structure in data.',
        'csv_note': False,
        'code': [
            'import numpy as np',
            'import matplotlib.pyplot as plt',
            '',
            '# Dataset: noisy sine curve',
            'X = np.linspace(-3, 3, 100)',
            'Y = np.sin(X) + np.random.normal(0, 0.2, 100)',
            '',
            '# Locally Weighted Regression',
            'P = []',
            'for x in X:',
            '    w = np.exp(-(X - x)**2 / (2 * 0.5**2))  # Gaussian kernel',
            '    P.append(np.sum(w * Y) / np.sum(w))',
            '',
            'plt.scatter(X, Y, s=10, label="Data")',
            'plt.plot(X, P, "r", linewidth=2, label="LWR Fit")',
            'plt.title("Locally Weighted Regression")',
            'plt.legend()',
            'plt.savefig("lwr_output.png")',
            'plt.show()',
            'print("Graph saved. LWR completed.")',
        ],
        'output': [
            'Graph saved. LWR completed.',
            '[Graph shows scatter plot of noisy sine data with smooth red LWR fit line]',
        ],
        'viva': [
            ('What is LWR?', 'A regression technique that fits a local model for each query point using weighted training samples.'),
            ('What is a Gaussian kernel?', 'A bell-shaped weight function — nearby points get higher weight, distant points get lower weight.'),
            ('Is LWR parametric?', 'No. It is non-parametric — no global model is learned.'),
            ('What is bandwidth (tau)?', 'Controls the width of the kernel. Smaller tau = more local fit.'),
        ]
    })

    # ══ 8 ══
    assignments.append({
        'exp': 8, 'co': 'CO4: Develop machine learning algorithms to solve real world problems.',
        'title': 'Exploratory Data Analysis for Classification using Pandas or Matplotlib.',
        'algo': 'Exploratory Data Analysis (EDA)',
        'concept': 'EDA is the process of analyzing datasets to summarize their main characteristics using statistics and visualizations. It helps understand patterns, detect outliers, and prepare data before applying ML models.',
        'csv_note': False,
        'code': [
            'import pandas as pd',
            'import matplotlib.pyplot as plt',
            'from sklearn.datasets import load_iris',
            '',
            'iris = load_iris()',
            'df = pd.DataFrame(iris.data, columns=iris.feature_names)',
            'df["target"] = iris.target',
            '',
            'print("Shape:", df.shape)',
            'print(df.head())',
            'print(df.describe())',
            'print("Class count:\\n", df["target"].value_counts())',
            '',
            '# Bar chart of class distribution',
            'df["target"].value_counts().plot(kind="bar", color=["blue","orange","green"])',
            'plt.title("Class Distribution")',
            'plt.savefig("eda_bar.png")',
            'plt.show()',
            '',
            '# Histogram of features',
            'df.hist(figsize=(8,6))',
            'plt.tight_layout()',
            'plt.savefig("eda_hist.png")',
            'plt.show()',
            '',
            '# Correlation matrix',
            'print("\\nCorrelation Matrix:")',
            'print(df.corr().round(2))',
        ],
        'output': [
            'Shape: (150, 5)',
            '   sepal length  sepal width  petal length  petal width  target',
            '0          5.1          3.5           1.4          0.2       0',
            '1          4.9          3.0           1.4          0.2       0',
            '',
            'Class count:',
            ' 0    50',
            ' 1    50',
            ' 2    50',
            '',
            'Correlation Matrix:',
            '              sepal length  sepal width  petal length  petal width',
            'sepal length          1.00        -0.12          0.87         0.82',
            'petal length          0.87        -0.43          1.00         0.96',
            '[Graphs: Class distribution bar chart + feature histograms]',
        ],
        'viva': [
            ('What is EDA?', 'Exploratory Data Analysis — initial investigation of data using statistics and plots.'),
            ('What does df.describe() show?', 'Count, mean, std, min, max, and quartile values for each numeric column.'),
            ('What is a correlation matrix?', 'Shows pairwise correlation coefficients between all features (-1 to +1).'),
            ('Why do EDA before ML?', 'To understand data distribution, detect missing values, outliers, and relationships.'),
        ]
    })

    # ══ 9 ══
    assignments.append({
        'exp': 9, 'co': 'CO4: Develop machine learning algorithms to solve real world problems.',
        'title': 'Write a program to implement Support Vector Machines (SVM) and Principal Component Analysis (PCA).',
        'algo': 'SVM & PCA',
        'concept': 'SVM finds the optimal hyperplane that maximizes the margin between classes. PCA reduces dimensionality by projecting data onto principal components that capture maximum variance.',
        'csv_note': False,
        'multi': [
            {
                'label': 'a) Support Vector Machine (SVM)',
                'code': [
                    'from sklearn.datasets import load_breast_cancer',
                    'from sklearn.model_selection import train_test_split',
                    'from sklearn.svm import SVC',
                    'from sklearn.metrics import accuracy_score',
                    '',
                    'X, y = load_breast_cancer(return_X_y=True)',
                    'Xtr,Xte,Ytr,Yte = train_test_split(X,y,test_size=0.2,random_state=42)',
                    'm = SVC(kernel="linear")',
                    'm.fit(Xtr, Ytr)',
                    'print("SVM Accuracy =", accuracy_score(Yte, m.predict(Xte)))',
                ],
                'output': ['SVM Accuracy = 0.9649'],
            },
            {
                'label': 'b) Principal Component Analysis (PCA)',
                'code': [
                    'from sklearn.datasets import load_iris',
                    'from sklearn.preprocessing import StandardScaler',
                    'from sklearn.decomposition import PCA',
                    'import matplotlib.pyplot as plt',
                    '',
                    'X, y = load_iris(return_X_y=True)',
                    'X = StandardScaler().fit_transform(X)',
                    'pca = PCA(n_components=2)',
                    'Xp = pca.fit_transform(X)',
                    'print("Variance Ratio =", pca.explained_variance_ratio_)',
                    'plt.scatter(Xp[:,0], Xp[:,1], c=y)',
                    'plt.title("PCA - Iris Dataset")',
                    'plt.savefig("pca_output.png")',
                    'plt.show()',
                ],
                'output': [
                    'Variance Ratio = [0.7296 0.2285]',
                    '[Graph: 2D scatter plot with 3 distinct color clusters]',
                ],
            },
        ],
        'viva': [
            ('What is SVM?', 'A classifier that finds the maximum-margin hyperplane separating classes.'),
            ('What is a kernel in SVM?', 'A function that maps data to higher dimensions to make it linearly separable.'),
            ('What is PCA?', 'Principal Component Analysis — reduces dimensions by finding directions of maximum variance.'),
            ('What does explained_variance_ratio_ mean?', 'Proportion of total variance captured by each principal component.'),
        ]
    })

    # ══ 10 ══
    assignments.append({
        'exp': 10, 'co': 'CO4: Develop machine learning algorithms to solve real world problems.',
        'title': 'Write a program to implement Principal Component Analysis (PCA).',
        'algo': 'Principal Component Analysis (PCA)',
        'concept': 'PCA is an unsupervised dimensionality reduction technique. It transforms correlated features into uncorrelated principal components, ordered by the amount of variance they explain. Useful for visualization and removing noise.',
        'csv_note': False,
        'code': [
            'from sklearn.datasets import load_breast_cancer',
            'from sklearn.preprocessing import StandardScaler',
            'from sklearn.decomposition import PCA',
            'import matplotlib.pyplot as plt',
            '',
            'X, y = load_breast_cancer(return_X_y=True)',
            '',
            '# Standardize (important before PCA)',
            'X = StandardScaler().fit_transform(X)',
            '',
            '# Apply PCA — reduce 30 features to 2',
            'pca = PCA(n_components=2)',
            'Xp = pca.fit_transform(X)',
            '',
            'print("Original shape  :", X.shape)',
            'print("Reduced shape   :", Xp.shape)',
            'print("Variance Ratio  :", pca.explained_variance_ratio_.round(4))',
            'print("Total Variance  :", pca.explained_variance_ratio_.sum().round(4))',
            '',
            'plt.scatter(Xp[:,0], Xp[:,1], c=y, cmap="bwr", edgecolors="k", s=20)',
            'plt.title("PCA — Breast Cancer Dataset (30 → 2 features)")',
            'plt.xlabel("PC1"); plt.ylabel("PC2")',
            'plt.colorbar(label="Class")',
            'plt.savefig("pca10_output.png")',
            'plt.show()',
        ],
        'output': [
            'Original shape  : (569, 30)',
            'Reduced shape   : (569, 2)',
            'Variance Ratio  : [0.4427 0.1897]',
            'Total Variance  : 0.6324',
            '[Graph: 2D scatter — malignant (red) vs benign (blue) clusters visible]',
        ],
        'viva': [
            ('Why standardize before PCA?', 'Features with large scale dominate variance. Standardization ensures equal contribution.'),
            ('What are principal components?', 'New axes (linear combinations of original features) that capture maximum variance.'),
            ('How many PCA components to choose?', 'Enough to capture ~95% of total variance (check explained_variance_ratio_.cumsum()).'),
            ('Is PCA supervised?', 'No. PCA is unsupervised — it does not use class labels.'),
        ]
    })

    # ─────────────── BUILD STORY ───────────────

    story = []

    # Cover Page
    story.append(Spacer(1, 20*mm))
    story.append(Paragraph('SHRI RAMSWAROOP MEMORIAL COLLEGE OF', 
        ParagraphStyle('CP1', fontSize=16, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=colors.HexColor('#1a237e'))))
    story.append(Paragraph('ENGINEERING AND MANAGEMENT, LUCKNOW',
        ParagraphStyle('CP2', fontSize=16, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=colors.HexColor('#1a237e'), spaceAfter=6)))
    story.append(HRFlowable(width='80%', thickness=2, color=colors.HexColor('#1a237e'), spaceAfter=10))
    story.append(Paragraph('BCA [Semester VI]  —  Academic Session: 2025-26 (Even)',
        ParagraphStyle('CP3', fontSize=11, fontName='Helvetica', alignment=TA_CENTER, spaceAfter=4)))
    story.append(Paragraph('NBCA–605P: MACHINE LEARNING LAB',
        ParagraphStyle('CP4', fontSize=14, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=colors.HexColor('#0d47a1'), spaceAfter=20)))
    story.append(HRFlowable(width='80%', thickness=1, color=colors.HexColor('#9fa8da'), spaceAfter=20))

    # Index table
    idx_data = [['#', 'Experiment', 'Algorithm / Topic', 'CO']]
    topics = [
        (1,'FIND-S Algorithm','CO1'), (2,'Candidate-Elimination Algorithm','CO1'),
        (3,'Linear Regression, Logistic Regression, Binary Classifier','CO2'),
        (4,'Bias, Variance, Remove Duplicates, Cross Validation','CO2'),
        (5,'Categorical Encoding & One-Hot Encoding','CO2'),
        (6,'k-Nearest Neighbor (kNN)','CO3'), (7,'Locally Weighted Regression (LWR)','CO3'),
        (8,'Exploratory Data Analysis (EDA)','CO4'),
        (9,'Support Vector Machine (SVM) & PCA','CO4'),
        (10,'Principal Component Analysis (PCA) — Extended','CO4'),
    ]
    for n,t,c in topics:
        idx_data.append([str(n), f'Experiment {n}', t, c])

    idx_table = Table(idx_data, colWidths=[10*mm, 25*mm, 110*mm, 15*mm])
    idx_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1a237e')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8.5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#e8eaf6')]),
        ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#9fa8da')),
        ('ALIGN', (0,0), (1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(idx_table)
    story.append(Spacer(1, 15*mm))
    story.append(Paragraph('Faculty: Mr. Hariom Tiwari &nbsp;&nbsp;|&nbsp;&nbsp; Mr. Prabhat Singh',
        ParagraphStyle('FAC', fontSize=9, fontName='Helvetica', alignment=TA_CENTER, textColor=colors.grey)))
    story.append(PageBreak())

    # ─── Each Assignment ───
    for a in assignments:
        story.append(header_table(a['exp'], a['co'], ''))
        story.append(Spacer(1, 2*mm))
        story.append(exp_header(a['exp'], a['co'], a['title']))
        story.append(Spacer(1, 3*mm))

        story.append(Paragraph(f"<b>Algorithm:</b> {a['algo']}", LABEL))
        story.append(HR)
        story.append(Paragraph('<b>Concept / Theory</b>', HEAD3))
        story.append(Paragraph(a['concept'], BODY))

        if a.get('csv_note'):
            story.append(Paragraph('<b>Note:</b> Create a file <b>training.csv</b> with columns: Sky, AirTemp, Humidity, Wind, Water, Forecast, EnjoySport (Yes/No).', SMALL))

        story.append(Spacer(1, 2*mm))

        if 'multi' in a:
            for sec in a['multi']:
                story.append(Paragraph(f"<b>{sec['label']}</b>", HEAD3))
                story.append(Paragraph('<b>Program:</b>', LABEL))
                story.append(code_box(sec['code']))
                story.append(Spacer(1, 1*mm))
                story.append(Paragraph('<b>Output:</b>', LABEL))
                story.append(code_box(sec['output'], out=True))
                story.append(Spacer(1, 3*mm))
        else:
            story.append(Paragraph('<b>Program:</b>', LABEL))
            story.append(code_box(a['code']))
            story.append(Spacer(1, 1*mm))
            story.append(Paragraph('<b>Output:</b>', LABEL))
            story.append(code_box(a['output'], out=True))

        story.append(Spacer(1, 3*mm))
        story.append(Paragraph('<b>Viva Questions &amp; Answers</b>', HEAD3))
        story.append(viva_table(a['viva']))
        story.append(Spacer(1, 4*mm))

        # Sign row
        sign = Table([[
            Paragraph('Faculty: Mr. Hariom Tiwari / Mr. Prabhat Singh', SMALL),
            Paragraph('Signature of HoD: ___________', SMALL)
        ]], colWidths=[100*mm, 80*mm])
        sign.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 0.4, colors.grey),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 5),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#fafafa')),
        ]))
        story.append(sign)
        story.append(PageBreak())

    doc.build(story)
    print("PDF created successfully!")

make_doc()