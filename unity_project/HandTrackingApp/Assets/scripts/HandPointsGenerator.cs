#if UNITY_EDITOR
using UnityEngine;
using UnityEditor;

/// <summary>
/// メニュー koten2026 > Create Hand Points から実行する。
/// OscManager に HandReceiver がアタッチされている前提。
/// </summary>
public static class HandPointsGenerator
{
    [MenuItem("koten2026/Create Hand Points")]
    static void CreateHandPoints()
    {
        var receiver = Object.FindFirstObjectByType<HandReceiver>();
        if (receiver == null)
        {
            Debug.LogError("[HandPointsGenerator] HandReceiver がシーンに見つかりません。OscManager にアタッチしてから実行してください。");
            return;
        }

        // マテリアル（Transparent）を作成
        var mat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        if (mat.HasProperty("_Surface"))
        {
            mat.SetFloat("_Surface", 1f); // 0=Opaque, 1=Transparent
            mat.SetFloat("_Blend", 0f);
            mat.enableInstancing = true;
            mat.renderQueue = 3000;
        }
        // Built-in の場合のフォールバック
        if (mat.shader.name == "Hidden/InternalErrorShader")
        {
            mat = new Material(Shader.Find("Standard"));
            mat.SetFloat("_Mode", 3f); // Transparent
        }
        AssetDatabase.CreateAsset(mat, "Assets/HandPointMaterial.mat");

        var leftPoints = CreatePoints("LeftHand", mat);
        var rightPoints = CreatePoints("RightHand", mat);

        receiver.leftWrist = leftPoints[0];
        receiver.leftIndexTip = leftPoints[1];
        receiver.rightWrist = rightPoints[0];
        receiver.rightIndexTip = rightPoints[1];
        receiver.leftRenderers = new[] { leftPoints[0].GetComponent<Renderer>(), leftPoints[1].GetComponent<Renderer>() };
        receiver.rightRenderers = new[] { rightPoints[0].GetComponent<Renderer>(), rightPoints[1].GetComponent<Renderer>() };

        EditorUtility.SetDirty(receiver);
        Debug.Log("[HandPointsGenerator] LeftHand / RightHand の2点を生成しました。");
    }

    static Transform[] CreatePoints(string parentName, Material mat)
    {
        var existing = GameObject.Find(parentName);
        if (existing != null) Object.DestroyImmediate(existing);

        var parent = new GameObject(parentName);
        Undo.RegisterCreatedObjectUndo(parent, "Create " + parentName);

        string[] names = { "wrist", "index_tip" };
        var points = new Transform[names.Length];
        for (int i = 0; i < names.Length; i++)
        {
            var sphere = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            sphere.name = names[i];
            sphere.transform.SetParent(parent.transform, false);
            sphere.transform.localScale = Vector3.one * 0.1f;
            sphere.GetComponent<Renderer>().sharedMaterial = mat;
            Object.DestroyImmediate(sphere.GetComponent<Collider>());
            points[i] = sphere.transform;
        }
        return points;
    }
}
#endif
